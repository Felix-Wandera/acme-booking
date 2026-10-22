from datetime import date, datetime, time, timedelta
from typing import List, Set
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import DoctorNotFoundError
from app.core.time_utils import (
    CLINIC_TZ,
    get_current_time,
    intervals_overlap,
    to_clinic_tz,
)
from app.models.appointment import Appointment, AppointmentStatus
from app.models.blocked_time import BlockedTime
from app.models.doctor import Doctor, DoctorWorkingHours
from app.schemas.doctor import DoctorAvailabilityResponse


class AvailabilityService:
    """Service responsible for calculating dynamic 30-minute appointment slot availability."""

    @classmethod
    def get_doctor_availability(
        cls,
        db: Session,
        doctor_id: uuid.UUID,
        target_date: date,
    ) -> DoctorAvailabilityResponse:
        """
        Calculate available 30-minute appointment slots for a doctor on a specific calendar date in Africa/Nairobi.
        Filters out:
        - Times outside doctor's set working intervals
        - Past times and times within the 1-hour booking buffer
        - Times overlapping doctor blocked periods (lunch breaks, leave)
        - Times with an existing active BOOKED appointment
        """
        # 1. Verify doctor exists
        doctor = db.get(Doctor, doctor_id)
        if not doctor:
            raise DoctorNotFoundError(f"Doctor with ID '{doctor_id}' does not exist.")

        # Inactive doctors cannot receive new bookings
        if not doctor.is_active:
            return DoctorAvailabilityResponse(
                doctor_id=doctor_id,
                date=target_date,
                timezone=settings.TIMEZONE,
                available_slots=[],
            )

        # 2. Get weekday (0=Monday, 6=Sunday)
        weekday = target_date.weekday()

        # 3. Retrieve working-hour intervals for this weekday
        working_intervals = db.scalars(
            select(DoctorWorkingHours)
            .where(
                DoctorWorkingHours.doctor_id == doctor_id,
                DoctorWorkingHours.day_of_week == weekday,
            )
            .order_by(DoctorWorkingHours.start_time)
        ).all()

        if not working_intervals:
            return DoctorAvailabilityResponse(
                doctor_id=doctor_id,
                date=target_date,
                timezone=settings.TIMEZONE,
                available_slots=[],
            )

        # 4. Generate candidate 30-minute slot start times from working intervals
        candidate_slots: List[datetime] = []
        slot_duration = timedelta(minutes=30)

        for interval in working_intervals:
            curr_dt = datetime.combine(target_date, interval.start_time, tzinfo=CLINIC_TZ)
            interval_end_dt = datetime.combine(target_date, interval.end_time, tzinfo=CLINIC_TZ)

            while curr_dt + slot_duration <= interval_end_dt:
                candidate_slots.append(curr_dt)
                curr_dt += slot_duration

        if not candidate_slots:
            return DoctorAvailabilityResponse(
                doctor_id=doctor_id,
                date=target_date,
                timezone=settings.TIMEZONE,
                available_slots=[],
            )

        # 5. Fetch doctor's blocked periods overlapping the date
        day_start = datetime.combine(target_date, time.min, tzinfo=CLINIC_TZ)
        day_end = datetime.combine(target_date, time.max, tzinfo=CLINIC_TZ)

        blocked_records = db.scalars(
            select(BlockedTime).where(
                BlockedTime.doctor_id == doctor_id,
                BlockedTime.start_time < day_end,
                BlockedTime.end_time > day_start,
            )
        ).all()

        # 6. Fetch existing BOOKED appointments for this doctor on this date
        booked_appointments = db.scalars(
            select(Appointment).where(
                Appointment.doctor_id == doctor_id,
                Appointment.status == AppointmentStatus.BOOKED,
                Appointment.start_time >= day_start,
                Appointment.start_time <= day_end,
            )
        ).all()

        booked_start_instants: Set[datetime] = {
            to_clinic_tz(appt.start_time) for appt in booked_appointments
        }

        # 7. Apply filtering rules
        now = get_current_time()
        buffer_cutoff = now + timedelta(hours=1)

        available_slots: List[datetime] = []
        for slot_start in candidate_slots:
            # Rule A: Minimum 1-hour booking buffer & not in the past
            if slot_start < buffer_cutoff:
                continue

            # Rule B: Slot already booked
            if slot_start in booked_start_instants:
                continue

            # Rule C: Overlap with blocked period
            slot_end = slot_start + slot_duration
            has_blocked_overlap = any(
                intervals_overlap(slot_start, slot_end, b.start_time, b.end_time)
                for b in blocked_records
            )
            if has_blocked_overlap:
                continue

            available_slots.append(slot_start)

        available_slots.sort()

        return DoctorAvailabilityResponse(
            doctor_id=doctor_id,
            date=target_date,
            timezone=settings.TIMEZONE,
            available_slots=available_slots,
        )
