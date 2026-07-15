from datetime import date, datetime, timedelta
from decimal import Decimal
from secrets import token_urlsafe
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models import Vehicle, MileageHistory, Expense, VehicleDocument, LinePairCode, User
from app.security import create_token, current_user, require_roles, verify_password

router = APIRouter(prefix="/api")
class LoginIn(BaseModel): email: EmailStr; password: str
class VehicleIn(BaseModel): name: str; plate_number: str; vehicle_type: str
class MileageIn(BaseModel): vehicle_id: int; mileage: int; note: str | None = None; ocr_status: str = "manual"
class ExpenseIn(BaseModel): vehicle_id: int; category: str; amount: Decimal; expense_date: date = date.today(); garage_name: str | None = None; note: str | None = None
class DocumentIn(BaseModel): vehicle_id: int; document_type: str; expiry_date: date

@router.post("/auth/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash): raise HTTPException(401, "อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    return {"token": create_token(user), "user": {"name": user.full_name, "role": user.role, "email": user.email}}
@router.get("/me")
def me(user=Depends(current_user)): return {"id":user.id,"name":user.full_name,"email":user.email,"role":user.role,"company_id":user.company_id}

@router.get("/dashboard")
def dashboard(vehicle_id: int | None = None, user=Depends(current_user), db: Session = Depends(get_db)):
    if vehicle_id:
        vehicle = db.get(Vehicle, vehicle_id)
        if not vehicle or vehicle.company_id != user.company_id:
            raise HTTPException(404, "ไม่พบยานพาหนะ")
        vehicle_ids = [vehicle.id]
    else:
        vehicle_ids = [x[0] for x in db.query(Vehicle.id).filter(Vehicle.company_id == user.company_id, Vehicle.is_active == True).all()]
        
    total_expense = db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.vehicle_id.in_(vehicle_ids), Expense.expense_date >= date.today().replace(day=1)).scalar()
    due_docs = db.query(VehicleDocument).filter(VehicleDocument.vehicle_id.in_(vehicle_ids), VehicleDocument.expiry_date <= date.today() + timedelta(days=30)).count()
    
    mileages = db.query(MileageHistory).filter(MileageHistory.vehicle_id.in_(vehicle_ids)).order_by(MileageHistory.recorded_at.desc()).limit(10).all()
    
    # Calculate monthly expenses per category for the last 6 months
    monthly_expenses = []
    today = date.today()
    for i in range(5, -1, -1):
        m_date = today - timedelta(days=i * 30)
        start_date = m_date.replace(day=1)
        next_month = (start_date + timedelta(days=32)).replace(day=1)
        end_date = next_month - timedelta(days=1)
        
        fuel = db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.vehicle_id.in_(vehicle_ids), Expense.category == "น้ำมันเชื้อเพลิง", Expense.expense_date.between(start_date, end_date)).scalar()
        maint = db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.vehicle_id.in_(vehicle_ids), Expense.category == "ค่าซ่อมบำรุง", Expense.expense_date.between(start_date, end_date)).scalar()
        parts = db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.vehicle_id.in_(vehicle_ids), Expense.category == "อะไหล่", Expense.expense_date.between(start_date, end_date)).scalar()
        other = db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.vehicle_id.in_(vehicle_ids), ~Expense.category.in_(["น้ำมันเชื้อเพลิง", "ค่าซ่อมบำรุง", "อะไหล่"]), Expense.expense_date.between(start_date, end_date)).scalar()
        
        monthly_expenses.append({
            "month": start_date.strftime("%m/%Y"),
            "fuel": float(fuel),
            "maintenance": float(maint),
            "parts": float(parts),
            "other": float(other)
        })
        
    # Calculate monthly mileage trend for the last 6 months
    mileage_trend = []
    for i in range(5, -1, -1):
        m_date = today - timedelta(days=i * 30)
        start_date = m_date.replace(day=1)
        next_month = (start_date + timedelta(days=32)).replace(day=1)
        end_date = next_month - timedelta(days=1)
        
        max_mil = db.query(func.max(MileageHistory.mileage)).filter(
            MileageHistory.vehicle_id.in_(vehicle_ids),
            MileageHistory.recorded_at <= datetime.combine(end_date, datetime.max.time())
        ).scalar()
        
        mileage_trend.append({
            "month": start_date.strftime("%m/%Y"),
            "mileage": max_mil or 0
        })
        
    return {
        "vehicles": len(vehicle_ids),
        "month_expense": float(total_expense),
        "due_documents": due_docs,
        "recent_mileage": [{"vehicle_id": x.vehicle_id, "mileage": x.mileage, "recorded_at": x.recorded_at} for x in mileages],
        "monthly_expenses": monthly_expenses,
        "mileage_trend": mileage_trend
    }

@router.get("/vehicles")
def vehicles(user=Depends(current_user), db: Session=Depends(get_db)):
    return db.query(Vehicle).filter(Vehicle.company_id==user.company_id, Vehicle.is_active==True).order_by(Vehicle.name).all()
@router.post("/vehicles")
def create_vehicle(payload:VehicleIn, user=Depends(require_roles("owner","admin","editor")), db:Session=Depends(get_db)):
    if payload.vehicle_type not in ("car","motorcycle"): raise HTTPException(422,"vehicle_type ต้องเป็น car หรือ motorcycle")
    item=Vehicle(company_id=user.company_id, **payload.model_dump()); db.add(item); db.commit(); db.refresh(item); return item

@router.post("/mileages")
def record_mileage(payload:MileageIn, user=Depends(require_roles("owner","admin","editor")), db:Session=Depends(get_db)):
    vehicle=db.get(Vehicle,payload.vehicle_id)
    if not vehicle or vehicle.company_id != user.company_id: raise HTTPException(404,"ไม่พบรถ")
    if payload.mileage < vehicle.current_mileage: raise HTTPException(422,f"เลขไมล์ใหม่ต้องไม่น้อยกว่า {vehicle.current_mileage:,} กม.")
    record=MileageHistory(recorded_by=user.id, source="web", **payload.model_dump()); vehicle.current_mileage=payload.mileage
    db.add(record); db.commit(); return {"message":"บันทึกเลขไมล์แล้ว","current_mileage":vehicle.current_mileage}
@router.get("/mileages")
def mileages(vehicle_id:int|None=None, user=Depends(current_user), db:Session=Depends(get_db)):
    q=db.query(MileageHistory).join(Vehicle).filter(Vehicle.company_id==user.company_id)
    if vehicle_id: q=q.filter(MileageHistory.vehicle_id==vehicle_id)
    return q.order_by(MileageHistory.recorded_at.desc()).limit(100).all()

@router.get("/expenses")
def expenses(user=Depends(current_user), db:Session=Depends(get_db)):
    return db.query(Expense).join(Vehicle).filter(Vehicle.company_id==user.company_id).order_by(Expense.expense_date.desc()).limit(100).all()
@router.post("/expenses")
def create_expense(payload:ExpenseIn,user=Depends(require_roles("owner","admin","editor")),db:Session=Depends(get_db)):
    vehicle=db.get(Vehicle,payload.vehicle_id)
    if not vehicle or vehicle.company_id != user.company_id: raise HTTPException(404,"ไม่พบรถ")
    item=Expense(created_by=user.id, **payload.model_dump()); db.add(item); db.commit(); db.refresh(item); return item

@router.get("/documents")
def documents(user=Depends(current_user), db:Session=Depends(get_db)):
    return db.query(VehicleDocument).join(Vehicle).filter(Vehicle.company_id==user.company_id).order_by(VehicleDocument.expiry_date).all()
@router.post("/documents")
def create_document(payload:DocumentIn,user=Depends(require_roles("owner","admin","editor")),db:Session=Depends(get_db)):
    vehicle=db.get(Vehicle,payload.vehicle_id)
    if not vehicle or vehicle.company_id != user.company_id: raise HTTPException(404,"ไม่พบรถ")
    item=VehicleDocument(**payload.model_dump()); db.add(item); db.commit(); db.refresh(item); return item

@router.post("/line/pair-code/{vehicle_id}")
def pair_code(vehicle_id:int,user=Depends(require_roles("owner","admin","editor")),db:Session=Depends(get_db)):
    vehicle=db.get(Vehicle,vehicle_id)
    if not vehicle or vehicle.company_id != user.company_id: raise HTTPException(404,"ไม่พบรถ")
    code=token_urlsafe(5).upper(); item=LinePairCode(vehicle_id=vehicle_id,code=code,expires_at=datetime.utcnow()+timedelta(minutes=10)); db.add(item); db.commit()
    return {"code":code,"expires_at":item.expires_at,"instruction":f"ส่งข้อความ LINE: ผูกรถ {code}"}

class ExpenseUpdate(BaseModel):
    vehicle_id: int | None = None
    category: str | None = None
    amount: Decimal | None = None
    expense_date: date | None = None
    garage_name: str | None = None
    note: str | None = None

class MileageUpdate(BaseModel):
    vehicle_id: int | None = None
    mileage: int | None = None
    note: str | None = None

@router.delete("/expenses/{id}")
def delete_expense(id: int, user=Depends(require_roles("owner","admin","editor")), db: Session = Depends(get_db)):
    item = db.get(Expense, id)
    if not item: raise HTTPException(404, "ไม่พบค่าใช้จ่าย")
    vehicle = db.get(Vehicle, item.vehicle_id)
    if not vehicle or vehicle.company_id != user.company_id: raise HTTPException(404, "ไม่พบค่าใช้จ่าย")
    db.delete(item)
    db.commit()
    return {"message": "ลบค่าใช้จ่ายเรียบร้อย"}

@router.patch("/expenses/{id}")
def update_expense(id: int, payload: ExpenseUpdate, user=Depends(require_roles("owner","admin","editor")), db: Session = Depends(get_db)):
    item = db.get(Expense, id)
    if not item: raise HTTPException(404, "ไม่พบค่าใช้จ่าย")
    vehicle = db.get(Vehicle, item.vehicle_id)
    if not vehicle or vehicle.company_id != user.company_id: raise HTTPException(404, "ไม่พบค่าใช้จ่าย")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item

@router.delete("/mileages/{id}")
def delete_mileage(id: int, user=Depends(require_roles("owner","admin","editor")), db: Session = Depends(get_db)):
    item = db.get(MileageHistory, id)
    if not item: raise HTTPException(404, "ไม่พบประวัติเลขไมล์")
    vehicle = db.get(Vehicle, item.vehicle_id)
    if not vehicle or vehicle.company_id != user.company_id: raise HTTPException(404, "ไม่พบประวัติเลขไมล์")
    db.delete(item)
    db.commit()
    return {"message": "ลบประวัติเลขไมล์เรียบร้อย"}

@router.patch("/mileages/{id}")
def update_mileage(id: int, payload: MileageUpdate, user=Depends(require_roles("owner","admin","editor")), db: Session = Depends(get_db)):
    item = db.get(MileageHistory, id)
    if not item: raise HTTPException(404, "ไม่พบประวัติเลขไมล์")
    vehicle = db.get(Vehicle, item.vehicle_id)
    if not vehicle or vehicle.company_id != user.company_id: raise HTTPException(404, "ไม่พบประวัติเลขไมล์")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item

