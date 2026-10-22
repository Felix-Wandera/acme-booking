from datetime import datetime
from typing import List, TYPE_CHECKING
import uuid

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.appointment import Appointment


class Patient(Base):
    """Patient entity registered at Acme Hospital Clinic."""
    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    appointments: Mapped[List["Appointment"]] = relationship(
        "Appointment",
        back_populates="patient",
    )

    def __repr__(self) -> str:
        return f"<Patient id={self.id} name='{self.name}' phone='{self.phone_number}'>"
