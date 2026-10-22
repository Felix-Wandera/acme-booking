from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class PatientBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, examples=["Jane Doe"])
    phone_number: str = Field(..., min_length=7, max_length=30, examples=["+254712345678"])


class PatientCreate(PatientBase):
    pass


class PatientResponse(PatientBase):
    id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
