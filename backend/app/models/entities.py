from datetime import datetime, date
from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base

class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    line_user_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(120))
    plate_number: Mapped[str] = mapped_column(String(30), index=True)
    vehicle_type: Mapped[str] = mapped_column(String(20)) # car | motorcycle
    current_mileage: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    users = relationship("UserVehicle", back_populates="vehicle", cascade="all, delete-orphan")

class UserVehicle(Base):
    __tablename__ = "user_vehicles"
    __table_args__ = (UniqueConstraint("user_id", "vehicle_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    vehicle = relationship("Vehicle", back_populates="users")

class MileageHistory(Base):
    __tablename__ = "mileage_histories"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    recorded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    mileage: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(20), default="web")
    ocr_status: Mapped[str] = mapped_column(String(20), default="manual") # pending, confirmed, corrected
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

class Expense(Base):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    category: Mapped[str] = mapped_column(String(50))
    amount: Mapped[float] = mapped_column(Numeric(12,2))
    expense_date: Mapped[date] = mapped_column(Date, default=date.today)
    garage_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    receipt_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class MaintenanceSchedule(Base):
    __tablename__ = "maintenance_schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    title: Mapped[str] = mapped_column(String(150))
    interval_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_performed_mileage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_performed_date: Mapped[date | None] = mapped_column(Date, nullable=True)

class MaintenanceLog(Base):
    __tablename__ = "maintenance_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("maintenance_schedules.id"))
    performed_date: Mapped[date] = mapped_column(Date, default=date.today)
    mileage: Mapped[int] = mapped_column(Integer)
    performed_early: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

class VehicleDocument(Base):
    __tablename__ = "vehicle_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    document_type: Mapped[str] = mapped_column(String(40)) # tax, insurance, compulsory_insurance, registration
    expiry_date: Mapped[date] = mapped_column(Date)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class LinePairCode(Base):
    __tablename__ = "line_pair_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

