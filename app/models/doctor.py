from datetime import datetime, time
from typing import List, TYPE_CHECKING
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, SmallInteger, String, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.blocked_time import BlockedTime


class Doctor(Base):
    """Doctor entity at Acme Hospital Clinic."""
    __tablename__ = "doctors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    working_hours: Mapped[List["DoctorWorkingHours"]] = relationship(
        "DoctorWorkingHours",
        back_populates="doctor",
        cascade="all, delete-orphan",
        order_by="DoctorWorkingHours.day_of_week, DoctorWorkingHours.start_time",
    )
    appointments: Mapped[List["Appointment"]] = relationship(
        "Appointment",
        back_populates="doctor",
    )
    blocked_periods: Mapped[List["BlockedTime"]] = relationship(
        "BlockedTime",
        back_populates="doctor",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Doctor id={self.id} name='{self.name}' is_active={self.is_active}>"


class DoctorWorkingHours(Base):
    """Weekly recurring working intervals for a doctor."""
    __tablename__ = "doctor_working_hours"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("doctors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_of_week: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="0=Monday through 6=Sunday",
    )
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    # Relationships
    doctor: Mapped["Doctor"] = relationship("Doctor", back_populates="working_hours")

    def __repr__(self) -> str:
        return (
            f"<DoctorWorkingHours doctor_id={self.doctor_id} "
            f"day={self.day_of_week} {self.start_time}-{self.end_time}>"
        )
