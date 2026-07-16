import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta
import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.line.webhook import analyze_image_with_gemini
from app.models import Expense, LinePairCode, LinePendingAction, MileageHistory, User, UserVehicle, Vehicle

router = APIRouter()

def verify_signature(raw: bytes, signature: str | None, secret: str) -> bool:
    if not signature or not secret: return False
    expected = base64.b64encode(hmac.new(secret.encode(), raw, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(expected, signature)

async def reply_line(reply_token: str, text: str, token: str, actions=None):
    message = {"type":"text","text":text[:5000]}
    if actions:
        message["quickReply"]={"items":[{"type":"action","action":{"type":"postback","label":label,"data":data,"displayText":label}} for label,data in actions]}
    payload={"replyToken":reply_token,"messages":[message]}
    async with httpx.AsyncClient(timeout=15.0) as client:
        response=await client.post("https://api.line.me/v2/bot/message/reply",json=payload,headers={"Content-Type":"application/json","Authorization":f"Bearer {token}"})
        response.raise_for_status()

def pending_summary(item, vehicle):
    if item.action_type=="odometer":
        return f"🤖 AI อ่านเลขไมล์ได้\n🚗 {vehicle.name} ({vehicle.plate_number})\n📈 {int(item.value):,} กม.\n\nกรุณาตรวจสอบก่อนบันทึก"
    return f"🤖 AI อ่านใบเสร็จได้\n🚗 {vehicle.name} ({vehicle.plate_number})\n🏷️ {item.category or 'อื่น ๆ'}\n💰 ฿{float(item.value):,.2f}\n🏪 {item.garage_name or '-'}\n\nกรุณาตรวจสอบก่อนบันทึก"

def action_buttons(item_id):
    return [("✅ ยืนยัน",f"ocr_confirm:{item_id}"),("✏️ แก้ไข",f"ocr_edit:{item_id}"),("❌ ยกเลิก",f"ocr_cancel:{item_id}")]

def owned_pending(db, item_id, line_id):
    return db.query(LinePendingAction).filter(LinePendingAction.id==item_id,LinePendingAction.line_user_id==line_id).first()

async def handle_postback(event, db, token, line_id):
    reply_token=event.get("replyToken");data=event.get("postback",{}).get("data","")
    try: command,raw_id=data.split(":",1);item_id=int(raw_id)
    except (ValueError,TypeError): return
    item=owned_pending(db,item_id,line_id)
    if not item:
        await reply_line(reply_token,"❌ ไม่พบรายการ OCR นี้",token);return
    if item.status!="pending" or item.expires_at<datetime.utcnow():
        await reply_line(reply_token,"ℹ️ รายการนี้ถูกดำเนินการแล้วหรือหมดอายุ",token);return
    if command=="ocr_cancel":
        item.status="cancelled";item.resolved_at=datetime.utcnow();db.commit()
        await reply_line(reply_token,"ยกเลิกรายการแล้ว ข้อมูลยังไม่ถูกบันทึก",token);return
    if command=="ocr_edit":
        unit="เลขไมล์ใหม่" if item.action_type=="odometer" else "ยอดเงินใหม่"
        await reply_line(reply_token,f"พิมพ์ข้อความตามรูปแบบนี้\nแก้ไข {item.id} {unit.replace('ใหม่','').strip()}\n\nตัวอย่าง: แก้ไข {item.id} 12500",token);return
    if command!="ocr_confirm": return
    vehicle=db.get(Vehicle,item.vehicle_id);user=db.get(User,item.user_id)
    if not vehicle or not user:
        await reply_line(reply_token,"❌ ไม่พบรถหรือผู้ใช้ของรายการนี้",token);return
    if item.action_type=="odometer":
        mileage=int(item.value)
        if mileage<vehicle.current_mileage:
            await reply_line(reply_token,f"❌ เลขไมล์ {mileage:,} น้อยกว่าค่าปัจจุบัน {vehicle.current_mileage:,} กรุณาแก้ไข",token,action_buttons(item.id));return
        db.add(MileageHistory(vehicle_id=vehicle.id,recorded_by=user.id,mileage=mileage,source="line",ocr_status="confirmed",image_path=item.image_path,note=item.note));vehicle.current_mileage=mileage
        result=f"✅ บันทึกเลขไมล์ {mileage:,} กม. สำเร็จ"
    else:
        db.add(Expense(vehicle_id=vehicle.id,created_by=user.id,category=item.category or "อื่น ๆ",amount=float(item.value),expense_date=datetime.now().date(),garage_name=item.garage_name,receipt_path=item.image_path,note=item.note))
        result=f"✅ บันทึกค่าใช้จ่าย ฿{float(item.value):,.2f} สำเร็จ"
    item.status="confirmed";item.resolved_at=datetime.utcnow();db.commit()
    await reply_line(reply_token,result,token)

async def handle_text(event, db, token, line_id):
    reply_token=event.get("replyToken");text=event.get("message",{}).get("text","").strip()
    if text.startswith("แก้ไข "):
        parts=text.split()
        if len(parts)!=3:
            await reply_line(reply_token,"รูปแบบไม่ถูกต้อง ตัวอย่าง: แก้ไข 12 12500",token);return
        try:item_id=int(parts[1]);value=float(parts[2])
        except ValueError:
            await reply_line(reply_token,"กรุณาระบุหมายเลขรายการและตัวเลขที่ถูกต้อง",token);return
        item=owned_pending(db,item_id,line_id)
        if not item or item.status!="pending" or item.expires_at<datetime.utcnow():
            await reply_line(reply_token,"❌ ไม่พบรายการที่แก้ไขได้",token);return
        if value<0:
            await reply_line(reply_token,"ค่าที่แก้ไขต้องไม่น้อยกว่า 0",token);return
        item.value=value;db.commit();vehicle=db.get(Vehicle,item.vehicle_id)
        await reply_line(reply_token,pending_summary(item,vehicle),token,action_buttons(item.id));return
    if not text.startswith("ผูกรถ "): return
    code=text.split(maxsplit=1)[1].upper()
    pair=db.query(LinePairCode).filter(LinePairCode.code==code,LinePairCode.used_at==None,LinePairCode.expires_at>datetime.utcnow()).first()
    if not pair:
        await reply_line(reply_token,"❌ ไม่พบรหัสยืนยันนี้ หรือรหัสหมดอายุแล้ว",token);return
    vehicle=db.get(Vehicle,pair.vehicle_id);user=db.query(User).filter(User.line_user_id==line_id).first()
    if not user and vehicle:
        candidates=db.query(User).filter(User.company_id==vehicle.company_id,User.line_user_id==None).all()
        if len(candidates)==1:user=candidates[0];user.line_user_id=line_id
    if not vehicle or not user:
        await reply_line(reply_token,"❌ ผูกบัญชีไม่ได้ กรุณาให้ผู้ดูแลตรวจสอบผู้ใช้ เพราะพบบัญชีที่เป็นไปได้มากกว่าหนึ่งบัญชี",token);return
    existing=db.query(UserVehicle).filter(UserVehicle.user_id==user.id,UserVehicle.vehicle_id==vehicle.id).first()
    if not existing:db.add(UserVehicle(user_id=user.id,vehicle_id=vehicle.id))
    pair.used_at=datetime.utcnow();db.commit()
    await reply_line(reply_token,f"✅ ผูกรถสำเร็จ\n🚗 {vehicle.name} ({vehicle.plate_number})\n👤 {user.full_name}",token)

async def handle_image(event, db, token, gemini_key, gemini_model, line_id):
    reply_token=event.get("replyToken");user=db.query(User).filter(User.line_user_id==line_id).first()
    if not user:
        await reply_line(reply_token,"❌ กรุณาผูกบัญชีก่อนส่งรูป",token);return
    links=db.query(UserVehicle).filter(UserVehicle.user_id==user.id).all()
    if not links:
        await reply_line(reply_token,"❌ ยังไม่มีรถที่ผูกกับบัญชีนี้",token);return
    vehicle=db.get(Vehicle,links[0].vehicle_id)
    message_id=str(event.get("message",{}).get("id", ""))
    existing=db.query(LinePendingAction).filter(LinePendingAction.message_id==message_id,LinePendingAction.line_user_id==line_id).first()
    if existing:
        await reply_line(reply_token,pending_summary(existing,vehicle),token,action_buttons(existing.id));return
    if not gemini_key:
        await reply_line(reply_token,"❌ ระบบยังไม่ได้ตั้งค่า GEMINI_API_KEY",token);return
    image_url=f"https://api-data.line.me/v2/bot/message/{message_id}/content"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response=await client.get(image_url,headers={"Authorization":f"Bearer {token}"})
        if response.status_code!=200:
            await reply_line(reply_token,"❌ ดาวน์โหลดรูปภาพไม่สำเร็จ",token);return
        image_bytes=response.content
    safe_id="".join(char for char in message_id if char.isalnum() or char in ("-","_"))
    if not safe_id:
        await reply_line(reply_token,"❌ รหัสรูปภาพไม่ถูกต้อง",token);return
    upload_dir=os.getenv("UPLOAD_DIR","uploads");os.makedirs(upload_dir,exist_ok=True);filename=f"line_{safe_id}.jpg";path=os.path.join(upload_dir,filename)
    with open(path,"wb") as image_file:image_file.write(image_bytes)
    try:analysis=await analyze_image_with_gemini(image_bytes,gemini_key,gemini_model)
    except Exception:
        await reply_line(reply_token,"❌ AI ประมวลผลรูปภาพไม่สำเร็จ กรุณาลองใหม่",token);return
    action_type=analysis.get("type");value=analysis.get("value")
    if action_type not in ("odometer","receipt") or value is None:
        await reply_line(reply_token,"ไม่สามารถจำแนกรูปได้ กรุณาส่งรูปหน้าปัดหรือใบเสร็จที่ชัดเจน",token);return
    pending=LinePendingAction(user_id=user.id,vehicle_id=vehicle.id,line_user_id=line_id,message_id=message_id,action_type=action_type,value=float(value),category=analysis.get("category"),garage_name=analysis.get("garage_name"),note=analysis.get("note"),image_path=f"/uploads/{filename}",status="pending",expires_at=datetime.utcnow()+timedelta(minutes=30))
    db.add(pending);db.commit();db.refresh(pending)
    await reply_line(reply_token,pending_summary(pending,vehicle),token,action_buttons(pending.id))

@router.post("/webhook/line")
async def line_webhook(request:Request,x_line_signature:str|None=Header(default=None)):
    raw=await request.body();secret=os.getenv("LINE_CHANNEL_SECRET","")
    if not secret:raise HTTPException(503,"LINE_CHANNEL_SECRET is not configured")
    if not verify_signature(raw,x_line_signature,secret):raise HTTPException(400,"Invalid LINE signature")
    try:body=json.loads(raw)
    except json.JSONDecodeError:raise HTTPException(400,"Invalid JSON")
    token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN","")
    if not token:raise HTTPException(503,"LINE_CHANNEL_ACCESS_TOKEN is not configured")
    for event in body.get("events",[]):
        reply_token=event.get("replyToken");line_id=event.get("source",{}).get("userId")
        if not reply_token or not line_id:continue
        db:Session=SessionLocal()
        try:
            if event.get("type")=="postback":await handle_postback(event,db,token,line_id)
            elif event.get("type")=="message" and event.get("message",{}).get("type")=="text":await handle_text(event,db,token,line_id)
            elif event.get("type")=="message" and event.get("message",{}).get("type")=="image":await handle_image(event,db,token,os.getenv("GEMINI_API_KEY",""),os.getenv("GEMINI_MODEL","gemini-3.1-flash-lite"),line_id)
        finally:db.close()
    return {"ok":True}
