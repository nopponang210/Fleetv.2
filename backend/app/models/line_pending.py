from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base

class LinePendingAction(Base):
    __tablename__ = "line_pending_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    line_user_id: Mapped[str] = mapped_column(String(100), index=True)
    message_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True, nullable=True)
    action_type: Mapped[str] = mapped_column(String(20))
    value: Mapped[float] = mapped_column(Numeric(12, 2))
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    garage_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
