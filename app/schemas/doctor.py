from datetime import date, datetime, time
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class DoctorWorkingHoursResponse(BaseModel):
    id: uuid.UUID
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday through 6=Sunday")
    start_time: time
    end_time: time

    model_config = ConfigDict(from_attributes=True)


class DoctorResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool
    created_at: datetime
    working_hours: Optional[List[DoctorWorkingHoursResponse]] = None

    model_config = ConfigDict(from_attributes=True)


class DoctorAvailabilityResponse(BaseModel):
    doctor_id: uuid.UUID
    date: date
    timezone: str = "Africa/Nairobi"
    available_slots: List[datetime] = Field(
        default_factory=list,
        description="List of available 30-minute start times with timezone offset",
    )
