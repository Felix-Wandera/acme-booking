from datetime import date
import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidDateError
from app.db.deps import get_db
from app.schemas.common import ErrorResponse
from app.schemas.doctor import DoctorAvailabilityResponse
from app.services.availability_service import AvailabilityService

router = APIRouter()


@router.get(
    "/{doctor_id}/availability",
    response_model=DoctorAvailabilityResponse,
    status_code=status.HTTP_200_OK,
    summary="Get doctor availability for a given date",
    description=(
        "Returns available 30-minute appointment start times for a doctor on a specific "
        "calendar date in the Africa/Nairobi timezone."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Doctor not found"},
        422: {"model": ErrorResponse, "description": "Invalid date format"},
    },
)
def get_doctor_availability(
    doctor_id: uuid.UUID,
    date_str: str = Query(
        ...,
        alias="date",
        description="Calendar date in YYYY-MM-DD format",
        examples=["2026-10-23"],
    ),
    db: Session = Depends(get_db),
) -> DoctorAvailabilityResponse:
    """Retrieve available 30-minute booking slots for a doctor on a given date."""
    try:
        parsed_date = date.fromisoformat(date_str)
    except ValueError:
        raise InvalidDateError("Date parameter must be a valid ISO-8601 date in YYYY-MM-DD format.")

    return AvailabilityService.get_doctor_availability(
        db=db,
        doctor_id=doctor_id,
        target_date=parsed_date,
    )
