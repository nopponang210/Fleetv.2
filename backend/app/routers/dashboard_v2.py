from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models import Expense, MaintenanceLog, MaintenanceSchedule, MileageHistory, Vehicle, VehicleDocument
from app.security import current_user, require_roles

router = APIRouter(prefix="/api")

class ScheduleIn(BaseModel):
    vehicle_id: int
    title: str
    interval_km: int | None = None
    interval_days: int | None = None
    last_performed_mileage: int | None = None
    last_performed_date: date | None = None

class CompleteIn(BaseModel):
    mileage: int
    performed_date: date = date.today()
    note: str | None = None

def month_start(value, offset):
    index = value.year * 12 + value.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)

def status(schedule, vehicle, today):
    due_mileage = (schedule.last_performed_mileage or 0) + schedule.interval_km if schedule.interval_km else None
    due_date = schedule.last_performed_date + timedelta(days=schedule.interval_days) if schedule.last_performed_date and schedule.interval_days else None
    overdue = (due_mileage is not None and vehicle.current_mileage >= due_mileage) or (due_date is not None and today > due_date)
    near = (due_mileage is not None and vehicle.current_mileage >= due_mileage - max(1, round(schedule.interval_km * .1))) or (due_date is not None and today >= due_date - timedelta(days=30))
    return {"id":schedule.id,"vehicle_id":vehicle.id,"vehicle_name":vehicle.name,"plate_number":vehicle.plate_number,"title":schedule.title,"state":"overdue" if overdue else "due" if near else "ok","current_mileage":vehicle.current_mileage,"due_mileage":due_mileage,"due_date":due_date,"last_performed_mileage":schedule.last_performed_mileage,"last_performed_date":schedule.last_performed_date}

@router.get("/dashboard")
def dashboard(vehicle_id:int|None=None, user=Depends(current_user), db:Session=Depends(get_db)):
    q=db.query(Vehicle).filter(Vehicle.company_id==user.company_id)
    if vehicle_id:q=q.filter(Vehicle.id==vehicle_id)
    vehicles=q.all()
    if vehicle_id and not vehicles:raise HTTPException(404,"ไม่พบยานพาหนะ")
    ids=[v.id for v in vehicles];today=date.today()
    month_expense=db.query(func.coalesce(func.sum(Expense.amount),0)).filter(Expense.vehicle_id.in_(ids),Expense.expense_date>=today.replace(day=1)).scalar()
    docs=db.query(VehicleDocument,Vehicle).join(Vehicle).filter(Vehicle.id.in_(ids),VehicleDocument.expiry_date<=today+timedelta(days=30)).order_by(VehicleDocument.expiry_date).all()
    doc_alerts=[{"state":"overdue" if d.expiry_date<today else "due","title":f"{d.document_type} {'หมดอายุแล้ว' if d.expiry_date<today else 'ใกล้หมดอายุ'}","detail":f"{v.name} · {v.plate_number}"} for d,v in docs]
    all_maintenance=[status(s,v,today) for s,v in db.query(MaintenanceSchedule,Vehicle).join(Vehicle).filter(Vehicle.id.in_(ids)).all()]
    maintenance=[x for x in all_maintenance if x["state"]!="ok"]
    monthly=[];mileage=[]
    for offset in range(-5,1):
        start=month_start(today,offset);end=month_start(today,offset+1)-timedelta(days=1)
        def cat_total(category=None):
            query=db.query(func.coalesce(func.sum(Expense.amount),0)).filter(Expense.vehicle_id.in_(ids),Expense.expense_date.between(start,end))
            return query.filter(Expense.category==category).scalar() if category else query.filter(~Expense.category.in_(["น้ำมันเชื้อเพลิง","ค่าซ่อมบำรุง","อะไหล่"])).scalar()
        monthly.append({"month":start.strftime("%m/%Y"),"fuel":float(cat_total("น้ำมันเชื้อเพลิง")),"maintenance":float(cat_total("ค่าซ่อมบำรุง")),"parts":float(cat_total("อะไหล่")),"other":float(cat_total())})
        maximum=db.query(func.max(MileageHistory.mileage)).filter(MileageHistory.vehicle_id.in_(ids),MileageHistory.recorded_at<=datetime.combine(end,datetime.max.time())).scalar()
        mileage.append({"month":start.strftime("%m/%Y"),"mileage":maximum or 0})
    recent=[]
    for m,v in db.query(MileageHistory,Vehicle).join(Vehicle).filter(Vehicle.id.in_(ids)).order_by(MileageHistory.recorded_at.desc()).limit(5):recent.append({"title":"บันทึกเลขไมล์","detail":f"{v.name} · {m.mileage:,} กม.","at":m.recorded_at})
    for e,v in db.query(Expense,Vehicle).join(Vehicle).filter(Vehicle.id.in_(ids)).order_by(Expense.created_at.desc()).limit(5):recent.append({"title":e.category,"detail":f"{v.name} · ฿{float(e.amount):,.2f}","at":e.created_at})
    recent.sort(key=lambda x:x["at"],reverse=True)
    by_vehicle=[{"name":v.name,"plate_number":v.plate_number,"amount":float(db.query(func.coalesce(func.sum(Expense.amount),0)).filter(Expense.vehicle_id==v.id,Expense.expense_date>=today.replace(day=1)).scalar())} for v in vehicles]
    return {"vehicles":len(vehicles),"active_vehicles":sum(v.is_active for v in vehicles),"inactive_vehicles":sum(not v.is_active for v in vehicles),"month_expense":float(month_expense),"due_documents":len(doc_alerts),"document_alerts":doc_alerts,"maintenance":maintenance,"maintenance_overdue":sum(x["state"]=="overdue" for x in maintenance),"monthly_expenses":monthly,"mileage_trend":mileage,"recent":recent[:8],"expense_by_vehicle":by_vehicle}

@router.get("/maintenance-schedules")
def list_schedules(vehicle_id:int|None=None,user=Depends(current_user),db:Session=Depends(get_db)):
    q=db.query(MaintenanceSchedule,Vehicle).join(Vehicle).filter(Vehicle.company_id==user.company_id)
    if vehicle_id:q=q.filter(Vehicle.id==vehicle_id)
    return [status(s,v,date.today()) for s,v in q.order_by(Vehicle.name,MaintenanceSchedule.title).all()]

@router.post("/maintenance-schedules")
def create_schedule(payload:ScheduleIn,user=Depends(require_roles("owner","admin","editor")),db:Session=Depends(get_db)):
    vehicle=db.get(Vehicle,payload.vehicle_id)
    if not vehicle or vehicle.company_id!=user.company_id:raise HTTPException(404,"ไม่พบรถ")
    if not payload.interval_km and not payload.interval_days:raise HTTPException(422,"ต้องระบุรอบตามเลขไมล์หรือจำนวนวันอย่างน้อยหนึ่งรายการ")
    item=MaintenanceSchedule(**payload.model_dump());db.add(item);db.commit();db.refresh(item);return status(item,vehicle,date.today())

@router.post("/maintenance-schedules/{schedule_id}/complete")
def complete(schedule_id:int,payload:CompleteIn,user=Depends(require_roles("owner","admin","editor")),db:Session=Depends(get_db)):
    schedule=db.get(MaintenanceSchedule,schedule_id);vehicle=db.get(Vehicle,schedule.vehicle_id) if schedule else None
    if not schedule or not vehicle or vehicle.company_id!=user.company_id:raise HTTPException(404,"ไม่พบรอบบำรุงรักษา")
    early=schedule.last_performed_mileage is not None and payload.mileage<schedule.last_performed_mileage+(schedule.interval_km or 0)
    db.add(MaintenanceLog(schedule_id=schedule.id,performed_date=payload.performed_date,mileage=payload.mileage,note=payload.note,performed_early=early));schedule.last_performed_mileage=payload.mileage;schedule.last_performed_date=payload.performed_date;db.commit()
    return {"message":"บันทึกการบำรุงรักษาแล้ว","schedule":status(schedule,vehicle,date.today())}
