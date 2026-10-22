from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.appointment import AppointmentStatus


class AppointmentCreate(BaseModel):
    doctor_id: uuid.UUID = Field(..., description="Target doctor's UUID")
    patient_id: uuid.UUID = Field(..., description="Booking patient's UUID")
    start_time: datetime = Field(
        ...,
        description="Appointment start instant in ISO-8601 with timezone offset",
        examples=["2026-10-23T10:00:00+03:00"],
    )


class AppointmentCancelRequest(BaseModel):
    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Required reason for appointment cancellation",
        examples=["Patient requested cancellation"],
    )


class AppointmentRescheduleRequest(BaseModel):
    new_start_time: datetime = Field(
        ...,
        description="New appointment start instant in ISO-8601 with timezone offset",
        examples=["2026-10-23T11:30:00+03:00"],
    )


class AppointmentResponse(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    patient_id: uuid.UUID
    start_time: datetime
    status: AppointmentStatus
    cancellation_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
