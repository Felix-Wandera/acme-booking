from datetime import datetime, timedelta
from typing import List, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AppointmentAlreadyCancelledError,
    AppointmentAlreadyStartedError,
    AppointmentNotFoundError,
    BlockedTimeOverlapError,
    DoctorInactiveError,
    DoctorNotFoundError,
    OutsideWorkingHoursError,
    PatientNotFoundError,
    SlotUnavailableError,
    ValidationError,
)
from app.core.time_utils import (
    get_current_time,
    intervals_overlap,
    slot_fits_working_interval,
    to_clinic_tz,
    validate_booking_buffer,
    validate_slot_alignment,
)
from app.db.base import utc_now
from app.models.appointment import Appointment, AppointmentStatus
from app.models.blocked_time import BlockedTime
from app.models.doctor import Doctor, DoctorWorkingHours
from app.models.patient import Patient


class BookingService:
    """Service coordinating transactional appointment booking, cancellation, and rescheduling."""

    @classmethod
    def book_appointment(
        cls,
        db: Session,
        doctor_id: uuid.UUID,
        patient_id: uuid.UUID,
        start_time: datetime,
    ) -> Appointment:
        """
        Book a 30-minute appointment slot for a doctor and patient.
        Follows strict transaction serialization with doctor row-locking (SELECT ... FOR UPDATE)
        and guards against race conditions with the database partial unique index.
        """
        # 1. Row-level lock on the doctor row to serialize concurrent booking mutations per doctor
        doctor = db.execute(
            select(Doctor).where(Doctor.id == doctor_id).with_for_update()
        ).scalar_one_or_none()

        if not doctor:
            raise DoctorNotFoundError(f"Doctor with ID '{doctor_id}' does not exist.")

        if not doctor.is_active:
            raise DoctorInactiveError("Doctor is inactive and cannot receive new bookings.")

        # 2. Verify patient exists
        patient = db.get(Patient, patient_id)
        if not patient:
            raise PatientNotFoundError(f"Patient with ID '{patient_id}' does not exist.")

        # 3. Validate slot timing rules
        norm_start = to_clinic_tz(start_time)
        validate_slot_alignment(norm_start)
        validate_booking_buffer(norm_start)

        slot_duration = timedelta(minutes=30)
        norm_end = norm_start + slot_duration

        # 4. Validate working hours for the target local weekday
        weekday = norm_start.weekday()
        working_hours = db.scalars(
            select(DoctorWorkingHours).where(
                DoctorWorkingHours.doctor_id == doctor_id,
                DoctorWorkingHours.day_of_week == weekday,
            )
        ).all()

        slot_start_time = norm_start.time()
        slot_end_time = norm_end.time()

        fits_working_hours = any(
            slot_fits_working_interval(
                slot_start_time,
                slot_end_time,
                wh.start_time,
                wh.end_time,
            )
            for wh in working_hours
        )
        if not fits_working_hours:
            raise OutsideWorkingHoursError(
                "Appointment does not fit within the doctor's working hours for that day."
            )

        # 5. Validate no overlap with doctor's blocked time
        overlapping_blocked = db.scalars(
            select(BlockedTime).where(
                BlockedTime.doctor_id == doctor_id,
                BlockedTime.start_time < norm_end,
                BlockedTime.end_time > norm_start,
            )
        ).first()

        if overlapping_blocked:
            raise BlockedTimeOverlapError(
                f"Requested slot overlaps with a doctor blocked period ({overlapping_blocked.reason})."
            )

        # 6. Check for existing active BOOKED appointment
        existing_booked = db.scalars(
            select(Appointment).where(
                Appointment.doctor_id == doctor_id,
                Appointment.start_time == norm_start,
                Appointment.status == AppointmentStatus.BOOKED,
            )
        ).first()

        if existing_booked:
            raise SlotUnavailableError("The selected slot is already booked.")

        # 7. Insert appointment and commit transaction
        appointment = Appointment(
            doctor_id=doctor_id,
            patient_id=patient_id,
            start_time=norm_start,
            status=AppointmentStatus.BOOKED,
        )
        db.add(appointment)

        try:
            db.commit()
            db.refresh(appointment)
            return appointment
        except IntegrityError:
            db.rollback()
            raise SlotUnavailableError(
                "The selected slot was taken by a concurrent booking request."
            )

    @classmethod
    def cancel_appointment(
        cls,
        db: Session,
        appointment_id: uuid.UUID,
        reason: str,
    ) -> Appointment:
        """
        Cancel an active appointment with a required reason.
        Enforces lock order: doctor row first, then appointment row.
        """
        cleaned_reason = reason.strip() if reason else ""
        if not cleaned_reason:
            raise ValidationError(
                code="INVALID_CANCELLATION_REASON",
                message="A non-empty cancellation reason must be provided.",
            )

        # Preliminary read to obtain immutable doctor_id
        appt_preview = db.get(Appointment, appointment_id)
        if not appt_preview:
            raise AppointmentNotFoundError(f"Appointment with ID '{appointment_id}' does not exist.")

        # Acquire doctor lock, then appointment lock (deterministic order)
        db.execute(
            select(Doctor).where(Doctor.id == appt_preview.doctor_id).with_for_update()
        )
        appointment = db.execute(
            select(Appointment).where(Appointment.id == appointment_id).with_for_update()
        ).scalar_one()

        # Invariant checks
        if appointment.status == AppointmentStatus.CANCELLED:
            raise AppointmentAlreadyCancelledError("Appointment has already been cancelled.")

        now = get_current_time()
        if to_clinic_tz(appointment.start_time) <= now:
            raise AppointmentAlreadyStartedError(
                "Appointments that have already started cannot be cancelled."
            )

        appointment.status = AppointmentStatus.CANCELLED
        appointment.cancellation_reason = cleaned_reason
        appointment.updated_at = utc_now()

        db.commit()
        db.refresh(appointment)
        return appointment

    @classmethod
    def reschedule_appointment(
        cls,
        db: Session,
        appointment_id: uuid.UUID,
        new_start_time: datetime,
    ) -> Appointment:
        """
        Reschedule an active appointment to a new slot for the same doctor.
        Re-validates all fresh-booking rules for the target slot atomically.
        """
        # Preliminary read to obtain doctor_id
        appt_preview = db.get(Appointment, appointment_id)
        if not appt_preview:
            raise AppointmentNotFoundError(f"Appointment with ID '{appointment_id}' does not exist.")

        # Deterministic lock order
        db.execute(
            select(Doctor).where(Doctor.id == appt_preview.doctor_id).with_for_update()
        )
        appointment = db.execute(
            select(Appointment).where(Appointment.id == appointment_id).with_for_update()
        ).scalar_one()

        if appointment.status == AppointmentStatus.CANCELLED:
            raise AppointmentAlreadyCancelledError("Cancelled appointments cannot be rescheduled.")

        now = get_current_time()
        if to_clinic_tz(appointment.start_time) <= now:
            raise AppointmentAlreadyStartedError(
                "Appointments that have already started cannot be rescheduled."
            )

        norm_new_start = to_clinic_tz(new_start_time)

        # If identical time, no-op return
        if norm_new_start == to_clinic_tz(appointment.start_time):
            return appointment

        # Validate new time boundaries and buffer
        validate_slot_alignment(norm_new_start)
        validate_booking_buffer(norm_new_start)

        slot_duration = timedelta(minutes=30)
        norm_new_end = norm_new_start + slot_duration

        # Validate working hours for new weekday
        weekday = norm_new_start.weekday()
        working_hours = db.scalars(
            select(DoctorWorkingHours).where(
                DoctorWorkingHours.doctor_id == appointment.doctor_id,
                DoctorWorkingHours.day_of_week == weekday,
            )
        ).all()

        slot_start_time = norm_new_start.time()
        slot_end_time = norm_new_end.time()

        fits_working_hours = any(
            slot_fits_working_interval(
                slot_start_time,
                slot_end_time,
                wh.start_time,
                wh.end_time,
            )
            for wh in working_hours
        )
        if not fits_working_hours:
            raise OutsideWorkingHoursError(
                "New appointment slot does not fit within doctor's working hours."
            )

        # Validate blocked periods
        overlapping_blocked = db.scalars(
            select(BlockedTime).where(
                BlockedTime.doctor_id == appointment.doctor_id,
                BlockedTime.start_time < norm_new_end,
                BlockedTime.end_time > norm_new_start,
            )
        ).first()

        if overlapping_blocked:
            raise BlockedTimeOverlapError(
                f"Target slot overlaps with a doctor blocked period ({overlapping_blocked.reason})."
            )

        # Check existing appointment in target slot (excluding current appointment)
        existing_booked = db.scalars(
            select(Appointment).where(
                Appointment.doctor_id == appointment.doctor_id,
                Appointment.start_time == norm_new_start,
                Appointment.status == AppointmentStatus.BOOKED,
                Appointment.id != appointment.id,
            )
        ).first()

        if existing_booked:
            raise SlotUnavailableError("Target slot is already booked.")

        appointment.start_time = norm_new_start
        appointment.updated_at = utc_now()

        try:
            db.commit()
            db.refresh(appointment)
            return appointment
        except IntegrityError:
            db.rollback()
            raise SlotUnavailableError("Target slot was taken by a concurrent request.")

    @classmethod
    def get_patient_upcoming_appointments(
        cls,
        db: Session,
        patient_id: uuid.UUID,
        limit: int = 10,
        offset: int = 0,
    ) -> List[Appointment]:
        """
        Return upcoming active appointments for a patient, sorted ascending by start_time.
        """
        patient = db.get(Patient, patient_id)
        if not patient:
            raise PatientNotFoundError(f"Patient with ID '{patient_id}' does not exist.")

        now = get_current_time()

        return list(
            db.scalars(
                select(Appointment)
                .where(
                    Appointment.patient_id == patient_id,
                    Appointment.status == AppointmentStatus.BOOKED,
                    Appointment.start_time > now,
                )
                .order_by(Appointment.start_time.asc())
                .limit(limit)
                .offset(offset)
            ).all()
        )
