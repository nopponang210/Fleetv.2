import os
import base64
import json
import httpx
from datetime import datetime
from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.models import LinePairCode, UserVehicle, User, MileageHistory, Vehicle, Expense

router = APIRouter()

async def reply_line(reply_token: str, text: str, token: str):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": text
            }
        ]
    }
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload, headers=headers)

async def analyze_image_with_gemini(image_bytes: bytes, api_key: str, model: str = "gemini-3.1-flash-lite"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    
    prompt = (
        "This is an image sent by a driver for a fleet management system.\n"
        "Analyze the image. It is either:\n"
        "1. A vehicle odometer/dashboard showing the current mileage.\n"
        "2. A receipt/invoice for vehicle expenses (like fuel/gas, repair, maintenance, battery, tires, insurance, registration, parking, toll/expressway, car wash, others).\n"
        "3. An irrelevant image.\n\n"
        "You must return a JSON object with the following fields:\n"
        '- "type": "odometer" | "receipt" | "unknown"\n'
        '- "value": integer (for mileage or total expense amount) or null\n'
        '- "category": string (MUST be one of these Thai categories if it is a receipt: "น้ำมันเชื้อเพลิง", "ค่าซ่อมบำรุง", "ยางรถ", "ประกันภัย", "ภาษีรถ", "พ.ร.บ.", "ล้างรถ", "ทางด่วน", "ที่จอดรถ", "ค่าปรับ", "อะไหล่", "แบตเตอรี่", "อุปกรณ์เสริม", "อื่น ๆ") or null\n'
        '- "garage_name": string (the merchant/gas station/garage name from the receipt) or null\n'
        '- "note": string (a short summary of the findings in Thai, e.g. "บันทึกเลขไมล์ 123,456 กม." or "ใบเสร็จค่าน้ำมัน 800 บาท จาก ปตท") or null\n\n'
        "Strictly return ONLY a valid JSON object."
    )
    
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {
                    "inlineData": {
                        "mimeType": "image/jpeg",
                        "data": image_b64
                    }
                }
            ]
        }],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            res_json = response.json()
            text_response = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
            if text_response.startswith("```"):
                lines = text_response.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                text_response = "\n".join(lines).strip()
            return json.loads(text_response)
        else:
            print(f"Gemini API Error details: Status {response.status_code}, Body: {response.text}")
            raise Exception(f"Gemini API returned status {response.status_code}: {response.text}")

async def analyze_text_with_gemini(text_content: str, api_key: str, model: str = "gemini-3.1-flash-lite"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    
    prompt = (
        "This is a text message sent by a driver for a fleet management system.\n"
        "Analyze the text message. It describes either:\n"
        "1. A vehicle odometer/mileage reading (e.g., 'เลขไมล์ 24500 กม' or 'วิ่งไป 123456 กม').\n"
        "2. A vehicle expense (e.g., 'ถ่ายน้ำมันเครื่อง 150 บาท ยี่ห้อเชลล์ป๋องเหลือง' or 'เติมน้ำมัน 800 บาท ปั๊มเอสโซ่').\n"
        "3. Irrelevant text.\n\n"
        "You must return a JSON object with the following fields:\n"
        '- "type": "odometer" | "receipt" | "unknown"\n'
        '- "value": integer (for mileage or total expense amount) or null\n'
        '- "category": string (MUST be one of these Thai categories if it is a receipt/expense: "น้ำมันเชื้อเพลิง", "ค่าซ่อมบำรุง", "ยางรถ", "ประกันภัย", "ภาษีรถ", "พ.ร.บ.", "ล้างรถ", "ทางด่วน", "ที่จอดรถ", "ค่าปรับ", "อะไหล่", "แบตเตอรี่", "อุปกรณ์เสริม", "อื่น ๆ") or null\n'
        '- "garage_name": string (the merchant/gas station/garage name mentioned in the message, if any) or null\n'
        '- "note": string (a short summary of the findings in Thai, e.g., "ถ่ายน้ำมันเครื่อง 150 บาท ยี่ห้อเชลล์ป๋องเหลือง" or the details mentioned in the text message) or null\n\n'
        "Strictly return ONLY a valid JSON object."
    )
    
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"text": f"Driver message: {text_content}"}
            ]
        }],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            res_json = response.json()
            text_response = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
            if text_response.startswith("```"):
                lines = text_response.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                text_response = "\n".join(lines).strip()
            return json.loads(text_response)
        else:
            print(f"Gemini API Error details: Status {response.status_code}, Body: {response.text}")
            raise Exception(f"Gemini API returned status {response.status_code}: {response.text}")

@router.post("/webhook/line")
async def line_webhook(request: Request, x_line_signature: str | None = Header(default=None)):
    body = await request.json()
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    
    for event in body.get("events", []):
        reply_token = event.get("replyToken")
        if not reply_token:
            continue
            
        message = event.get("message", {})
        msg_type = message.get("type")
        line_id = event.get("source", {}).get("userId")
        
        if event.get("type") != "message" or not line_id:
            continue
            
        db: Session = SessionLocal()
        try:
            if msg_type == "text":
                text = message.get("text", "").strip()
                if text.startswith("ผูกรถ "):
                    code = text.split(maxsplit=1)[1].upper()
                    pair = db.query(LinePairCode).filter(
                        LinePairCode.code == code,
                        LinePairCode.used_at == None,
                        LinePairCode.expires_at > datetime.utcnow()
                    ).first()
                    
                    if pair:
                        vehicle = db.get(Vehicle, pair.vehicle_id)
                        if vehicle:
                            user = db.query(User).filter(User.line_user_id == line_id).first()
                            if not user:
                                # Fallback: link the line_id to the first user of this company who isn't linked yet
                                user = db.query(User).filter(User.company_id == vehicle.company_id, User.line_user_id == None).first()
                                if user:
                                    user.line_user_id = line_id
                                    db.add(user)
                                    db.flush()
                            
                            if user:
                                # Check if already paired
                                existing = db.query(UserVehicle).filter(UserVehicle.user_id == user.id, UserVehicle.vehicle_id == vehicle.id).first()
                                if not existing:
                                    db.add(UserVehicle(user_id=user.id, vehicle_id=vehicle.id))
                                pair.used_at = datetime.utcnow()
                                db.commit()
                                await reply_line(reply_token, f"🤖 ผูกรถสำเร็จ!\n🚗 ยานพาหนะ: {vehicle.name} ({vehicle.plate_number})\n👤 ผู้ขับ: {user.full_name}", token)
                            else:
                                await reply_line(reply_token, "❌ ไม่สามารถผูกบัญชีได้ เนื่องจากไม่พบผู้ใช้ในระบบของบริษัทนี้", token)
                        else:
                            await reply_line(reply_token, "❌ ไม่สามารถผูกบัญชีได้ เนื่องจากไม่พบยานพาหนะนี้ในระบบ", token)
                    else:
                        await reply_line(reply_token, "❌ ไม่พบรหัสยืนยันนี้ หรือรหัสหมดอายุแล้ว", token)
                else:
                    # AI processing for raw driver text messages
                    user = db.query(User).filter(User.line_user_id == line_id).first()
                    if not user:
                        await reply_line(reply_token, "❌ กรุณาผูกบัญชีรถยนต์ของคุณก่อนพิมพ์ข้อความรายงานครับ\nโดยพิมพ์: ผูกรถ [รหัสยืนยันที่ได้รับจากระบบ]", token)
                        continue
                        
                    user_vehicle = db.query(UserVehicle).filter(UserVehicle.user_id == user.id).first()
                    if not user_vehicle:
                        await reply_line(reply_token, "❌ คุณยังไม่มีรถที่จับคู่ในระบบ กรุณาผูกรถก่อนครับ", token)
                        continue
                        
                    vehicle_id = user_vehicle.vehicle_id
                    vehicle = db.get(Vehicle, vehicle_id)
                    if not vehicle:
                        await reply_line(reply_token, "❌ ไม่พบข้อมูลรถยนต์ในระบบ", token)
                        continue

                    if not gemini_key:
                        await reply_line(reply_token, "❌ ระบบยังไม่ได้ตั้งค่า GEMINI_API_KEY", token)
                        continue
                        
                    try:
                        analysis = await analyze_text_with_gemini(text, gemini_key, gemini_model)
                        analysis_type = analysis.get("type")
                        value = analysis.get("value")
                        note = analysis.get("note", "")
                        
                        if analysis_type == "odometer" and value is not None:
                            # Check if mileage is valid
                            if value < vehicle.current_mileage:
                                await reply_line(reply_token, f"❌ เลขไมล์ที่ระบุ ({value:,} กม.) น้อยกว่าเลขไมล์ปัจจุบัน ({vehicle.current_mileage:,} กม.) กรุณาลองใหม่อีกครั้ง", token)
                                continue
                                
                            record = MileageHistory(
                                vehicle_id=vehicle_id,
                                recorded_by=user.id,
                                mileage=int(value),
                                source="line",
                                ocr_status="confirmed",
                                image_path=None,
                                note=note or text
                            )
                            vehicle.current_mileage = int(value)
                            db.add(record)
                            db.commit()
                            
                            await reply_line(reply_token, f"🤖 บันทึกเลขไมล์สำเร็จ!\n🚗 รถ: {vehicle.name} ({vehicle.plate_number})\n📈 เลขไมล์: {value:,} กม.\n📝 บันทึก: {note or text}", token)
                            
                        elif analysis_type == "receipt" and value is not None:
                            category = analysis.get("category", "อื่น ๆ")
                            garage_name = analysis.get("garage_name", "")
                            
                            record = Expense(
                                vehicle_id=vehicle_id,
                                created_by=user.id,
                                category=category,
                                amount=float(value),
                                expense_date=datetime.now().date(),
                                garage_name=garage_name,
                                receipt_path=None,
                                note=note or text
                            )
                            db.add(record)
                            db.commit()
                            
                            await reply_line(reply_token, f"🤖 บันทึกค่าใช้จ่ายสำเร็จ!\n🚗 รถ: {vehicle.name}\n🏷️ หมวดหมู่: {category}\n💰 ยอดเงิน: ฿{value:,}\n🏪 ร้านค้า: {garage_name or '-'}\n📝 บันทึก: {note or text}", token)
                        else:
                            await reply_line(reply_token, "🤖 บอทไม่เข้าใจข้อความนี้ (ไม่พบเลขไมล์หรือค่าใช้จ่าย)\nตัวอย่างพิมพ์รายงาน:\n- เติมน้ำมัน 800 บาท\n- ถ่ายน้ำมันเครื่อง 150 บาท\n- เลขไมล์สะสม 24500 กม", token)
                            
                    except Exception as gemini_err:
                        print(f"Gemini text processing error: {gemini_err}")
                        await reply_line(reply_token, "❌ เกิดข้อผิดพลาดในการประมวลผลข้อความด้วย AI กรุณาลองใหม่อีกครั้ง", token)

            elif msg_type == "image":
                # Find the user and vehicle paired
                user = db.query(User).filter(User.line_user_id == line_id).first()
                if not user:
                    await reply_line(reply_token, "❌ กรุณาผูกบัญชีรถยนต์ของคุณก่อนส่งรูปภาพครับ\nโดยพิมพ์: ผูกรถ [รหัสยืนยันที่ได้รับจากระบบ]", token)
                    continue
                    
                user_vehicle = db.query(UserVehicle).filter(UserVehicle.user_id == user.id).first()
                if not user_vehicle:
                    await reply_line(reply_token, "❌ คุณยังไม่มีรถที่จับคู่ในระบบ กรุณาผูกรถก่อนครับ", token)
                    continue
                    
                vehicle_id = user_vehicle.vehicle_id
                vehicle = db.get(Vehicle, vehicle_id)
                if not vehicle:
                    await reply_line(reply_token, "❌ ไม่พบข้อมูลรถยนต์ในระบบ", token)
                    continue

                if not token:
                    await reply_line(reply_token, "❌ ระบบยังไม่ได้ตั้งค่า LINE Channel Access Token", token)
                    continue
                    
                # Download image from LINE
                image_url = f"https://api-data.line.me/v2/bot/message/{message['id']}/content"
                headers = {"Authorization": f"Bearer {token}"}
                
                async with httpx.AsyncClient() as client:
                    img_response = await client.get(image_url, headers=headers)
                    if img_response.status_code != 200:
                        await reply_line(reply_token, "❌ ไม่สามารถดาวน์โหลดรูปภาพจากระบบ LINE ได้", token)
                        continue
                    image_bytes = img_response.content

                # Ensure uploads dir exists
                os.makedirs("uploads", exist_ok=True)
                filename = f"line_{message['id']}.jpg"
                file_path = os.path.join("uploads", filename)
                with open(file_path, "wb") as f:
                    f.write(image_bytes)
                
                # Call Gemini API
                if not gemini_key:
                    await reply_line(reply_token, "❌ ระบบยังไม่ได้ตั้งค่า GEMINI_API_KEY", token)
                    continue
                    
                try:
                    analysis = await analyze_image_with_gemini(image_bytes, gemini_key, gemini_model)
                    analysis_type = analysis.get("type")
                    value = analysis.get("value")
                    note = analysis.get("note", "")
                    
                    if analysis_type == "odometer" and value is not None:
                        # Check if mileage is valid
                        if value < vehicle.current_mileage:
                            await reply_line(reply_token, f"❌ เลขไมล์ที่อ่านได้ ({value:,} กม.) น้อยกว่าเลขไมล์ปัจจุบัน ({vehicle.current_mileage:,} กม.) กรุณาลองใหม่อีกครั้ง", token)
                            continue
                            
                        record = MileageHistory(
                            vehicle_id=vehicle_id,
                            recorded_by=user.id,
                            mileage=int(value),
                            source="line",
                            ocr_status="confirmed",
                            image_path=f"/uploads/{filename}",
                            note=note
                        )
                        vehicle.current_mileage = int(value)
                        db.add(record)
                        db.commit()
                        
                        await reply_line(reply_token, f"🤖 บันทึกเลขไมล์สำเร็จ!\n🚗 รถ: {vehicle.name} ({vehicle.plate_number})\n📈 เลขไมล์: {value:,} กม.\n📝 บันทึก: {note or 'อ่านอัตโนมัติ'}", token)
                        
                    elif analysis_type == "receipt" and value is not None:
                        category = analysis.get("category", "อื่น ๆ")
                        garage_name = analysis.get("garage_name", "")
                        
                        record = Expense(
                            vehicle_id=vehicle_id,
                            created_by=user.id,
                            category=category,
                            amount=float(value),
                            expense_date=datetime.now().date(),
                            garage_name=garage_name,
                            receipt_path=f"/uploads/{filename}",
                            note=note
                        )
                        db.add(record)
                        db.commit()
                        
                        await reply_line(reply_token, f"🤖 บันทึกค่าใช้จ่ายสำเร็จ!\n🚗 รถ: {vehicle.name}\n🏷️ หมวดหมู่: {category}\n💰 ยอดเงิน: ฿{value:,}\n🏪 ร้านค้า: {garage_name or '-'}\n📝 บันทึก: {note or 'บันทึกอัตโนมัติ'}", token)
                    else:
                        await reply_line(reply_token, f"🤖 ไม่สามารถจำแนกรูปภาพนี้ได้ (ระบบวิเคราะห์ว่าเป็น: {analysis_type})\nกรุณาส่งรูปภาพหน้าปัดรถยนต์หรือใบเสร็จรับเงินที่ชัดเจนครับ", token)
                        
                except Exception as gemini_err:
                    print(f"Gemini processing error: {gemini_err}")
                    await reply_line(reply_token, "❌ เกิดข้อผิดพลาดในการใช้ AI ประมวลผลรูปภาพ กรุณาลองใหม่อีกครั้ง", token)
                    
        except Exception as e:
            print(f"Webhook error: {e}")
        finally:
            db.close()
            
    return {"ok": True}
