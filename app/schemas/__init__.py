"""Pydantic schemas for requests, responses, and validation error models."""

from app.schemas.appointment import (
    AppointmentCancelRequest,
    AppointmentCreate,
    AppointmentRescheduleRequest,
    AppointmentResponse,
)
from app.schemas.blocked_time import BlockedTimeResponse
from app.schemas.common import ErrorDetail, ErrorResponse
from app.schemas.doctor import (
    DoctorAvailabilityResponse,
    DoctorResponse,
    DoctorWorkingHoursResponse,
)
from app.schemas.patient import PatientCreate, PatientResponse

__all__ = [
    "AppointmentCancelRequest",
    "AppointmentCreate",
    "AppointmentRescheduleRequest",
    "AppointmentResponse",
    "BlockedTimeResponse",
    "DoctorAvailabilityResponse",
    "DoctorResponse",
    "DoctorWorkingHoursResponse",
    "ErrorDetail",
    "ErrorResponse",
    "PatientCreate",
    "PatientResponse",
]
