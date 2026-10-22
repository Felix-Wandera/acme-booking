import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.schemas.appointment import (
    AppointmentCancelRequest,
    AppointmentCreate,
    AppointmentRescheduleRequest,
    AppointmentResponse,
)
from app.schemas.common import ErrorResponse
from app.services.booking_service import BookingService

router = APIRouter()


@router.post(
    "",
    response_model=AppointmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Book a new clinic appointment",
    description=(
        "Books a 30-minute appointment slot for a doctor and patient. "
        "Enforces doctor working hours, 1-hour advance booking buffer, "
        "30-minute slot alignment, blocked time checks, and transactional lock serialization."
    ),
    responses={
        201: {"model": AppointmentResponse, "description": "Appointment successfully booked"},
        404: {"model": ErrorResponse, "description": "Doctor or patient not found"},
        409: {"model": ErrorResponse, "description": "Doctor is inactive or slot is already booked"},
        422: {"model": ErrorResponse, "description": "Slot validation or scheduling rule failure"},
    },
)
def book_appointment(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
) -> AppointmentResponse:
    """Create a new appointment reservation."""
    return BookingService.book_appointment(
        db=db,
        doctor_id=payload.doctor_id,
        patient_id=payload.patient_id,
        start_time=payload.start_time,
    )


@router.patch(
    "/{appointment_id}/cancel",
    response_model=AppointmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel an active appointment",
    description=(
        "Cancels an active appointment with a mandatory cancellation reason. "
        "The slot becomes immediately bookable again for other patients. "
        "Appointments that have already started cannot be cancelled."
    ),
    responses={
        200: {"model": AppointmentResponse, "description": "Appointment successfully cancelled"},
        404: {"model": ErrorResponse, "description": "Appointment not found"},
        409: {"model": ErrorResponse, "description": "Appointment already cancelled or already started"},
        422: {"model": ErrorResponse, "description": "Invalid cancellation reason"},
    },
)
def cancel_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentCancelRequest,
    db: Session = Depends(get_db),
) -> AppointmentResponse:
    """Cancel an existing active appointment."""
    return BookingService.cancel_appointment(
        db=db,
        appointment_id=appointment_id,
        reason=payload.reason,
    )


@router.patch(
    "/{appointment_id}/reschedule",
    response_model=AppointmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Reschedule an active appointment",
    description=(
        "Moves an active appointment to a new 30-minute slot for the same doctor. "
        "Revalidates all scheduling rules against the target slot atomically. "
        "If validation or conflict occurs, the original booking remains untouched."
    ),
    responses={
        200: {"model": AppointmentResponse, "description": "Appointment successfully rescheduled"},
        404: {"model": ErrorResponse, "description": "Appointment not found"},
        409: {"model": ErrorResponse, "description": "Target slot already taken or appointment already cancelled"},
        422: {"model": ErrorResponse, "description": "Target slot violates scheduling rules"},
    },
)
def reschedule_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentRescheduleRequest,
    db: Session = Depends(get_db),
) -> AppointmentResponse:
    """Reschedule an existing active appointment."""
    return BookingService.reschedule_appointment(
        db=db,
        appointment_id=appointment_id,
        new_start_time=payload.new_start_time,
    )
