from typing import List
import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.schemas.appointment import AppointmentResponse
from app.schemas.common import ErrorResponse
from app.services.booking_service import BookingService

router = APIRouter()


@router.get(
    "/{patient_id}/appointments",
    response_model=List[AppointmentResponse],
    status_code=status.HTTP_200_OK,
    summary="Get upcoming appointments for a patient",
    description=(
        "Returns active BOOKED appointments for a patient with start times strictly in the future, "
        "sorted chronologically (ascending by start time). Supports limit and offset pagination."
    ),
    responses={
        200: {"description": "List of patient upcoming appointments"},
        404: {"model": ErrorResponse, "description": "Patient not found"},
        422: {"model": ErrorResponse, "description": "Invalid pagination parameters"},
    },
)
def get_patient_upcoming_appointments(
    patient_id: uuid.UUID,
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of upcoming appointments to return (1-100)",
        examples=[10],
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of appointments to skip for pagination (>=0)",
        examples=[0],
    ),
    db: Session = Depends(get_db),
) -> List[AppointmentResponse]:
    """Retrieve chronologically sorted upcoming appointments for a specific patient."""
    return BookingService.get_patient_upcoming_appointments(
        db=db,
        patient_id=patient_id,
        limit=limit,
        offset=offset,
    )
