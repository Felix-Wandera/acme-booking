from datetime import date, datetime, time, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.exceptions import (
    BookingBufferViolationError,
    InvalidSlotAlignmentError,
)

CLINIC_TZ = ZoneInfo(settings.TIMEZONE)

# Controllable clock reference for deterministic testing
_clock_override: Optional[datetime] = None


def get_current_time() -> datetime:
    """Return the current time in the clinic timezone, respecting any test clock override."""
    global _clock_override
    if _clock_override is not None:
        return to_clinic_tz(_clock_override)
    return datetime.now(CLINIC_TZ)


def set_system_time(dt: datetime) -> None:
    """Override the system clock for deterministic testing."""
    global _clock_override
    _clock_override = dt


def reset_system_time() -> None:
    """Reset the clock override back to the live system clock."""
    global _clock_override
    _clock_override = None


def to_clinic_tz(dt: datetime) -> datetime:
    """Normalize a datetime to the clinic timezone (Africa/Nairobi)."""
    if dt.tzinfo is None:
        # Interpret naive datetime as being in clinic timezone
        return dt.replace(tzinfo=CLINIC_TZ)
    return dt.astimezone(CLINIC_TZ)


def validate_slot_alignment(dt: datetime) -> None:
    """Verify that an appointment start time aligns to a 30-minute boundary with zero seconds."""
    localized = to_clinic_tz(dt)
    if localized.minute not in (0, 30) or localized.second != 0 or localized.microsecond != 0:
        raise InvalidSlotAlignmentError()


def validate_booking_buffer(dt: datetime, min_hours: int = 1) -> None:
    """Verify that an appointment is scheduled at least min_hours (default 1) in the future."""
    localized = to_clinic_tz(dt)
    now = get_current_time()
    min_allowed = now + timedelta(hours=min_hours)
    if localized < min_allowed:
        raise BookingBufferViolationError()


def get_slot_interval(start_time: datetime, duration_minutes: int = 30) -> Tuple[datetime, datetime]:
    """Calculate the half-open interval [start, end) for a slot."""
    start = to_clinic_tz(start_time)
    end = start + timedelta(minutes=duration_minutes)
    return start, end


def intervals_overlap(
    start1: datetime,
    end1: datetime,
    start2: datetime,
    end2: datetime,
) -> bool:
    """Check if two half-open intervals [start1, end1) and [start2, end2) overlap."""
    s1, e1 = to_clinic_tz(start1), to_clinic_tz(end1)
    s2, e2 = to_clinic_tz(start2), to_clinic_tz(end2)
    return max(s1, s2) < min(e1, e2)


def slot_fits_working_interval(
    slot_start: time,
    slot_end: time,
    work_start: time,
    work_end: time,
) -> bool:
    """Check if a 30-minute slot [slot_start, slot_end] fits completely within a working interval."""
    return slot_start >= work_start and slot_end <= work_end
