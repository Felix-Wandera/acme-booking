from typing import Optional


class AppException(Exception):
    """Base application exception carrying machine-readable code, message, and HTTP status."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


# 404 Not Found Exceptions
class NotFoundError(AppException):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=404)


class DoctorNotFoundError(NotFoundError):
    def __init__(self, message: str = "Doctor not found.") -> None:
        super().__init__(code="DOCTOR_NOT_FOUND", message=message)


class PatientNotFoundError(NotFoundError):
    def __init__(self, message: str = "Patient not found.") -> None:
        super().__init__(code="PATIENT_NOT_FOUND", message=message)


class AppointmentNotFoundError(NotFoundError):
    def __init__(self, message: str = "Appointment not found.") -> None:
        super().__init__(code="APPOINTMENT_NOT_FOUND", message=message)


# 409 Conflict Exceptions
class ConflictError(AppException):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=409)


class SlotUnavailableError(ConflictError):
    def __init__(
        self,
        message: str = "The selected slot is no longer available.",
    ) -> None:
        super().__init__(code="SLOT_UNAVAILABLE", message=message)


class DoctorInactiveError(ConflictError):
    def __init__(
        self,
        message: str = "Doctor is inactive and cannot receive new bookings.",
    ) -> None:
        super().__init__(code="DOCTOR_INACTIVE", message=message)


class AppointmentAlreadyCancelledError(ConflictError):
    def __init__(
        self,
        message: str = "Appointment has already been cancelled.",
    ) -> None:
        super().__init__(code="APPOINTMENT_ALREADY_CANCELLED", message=message)


class AppointmentAlreadyStartedError(ConflictError):
    def __init__(
        self,
        message: str = "Appointments that have already started cannot be cancelled or rescheduled.",
    ) -> None:
        super().__init__(code="APPOINTMENT_ALREADY_STARTED", message=message)


# 422 Unprocessable Entity Exceptions
class ValidationError(AppException):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=422)


class InvalidSlotAlignmentError(ValidationError):
    def __init__(
        self,
        message: str = "Start time must be aligned to a 30-minute boundary (:00 or :30) with zero seconds.",
    ) -> None:
        super().__init__(code="INVALID_SLOT_ALIGNMENT", message=message)


class BookingBufferViolationError(ValidationError):
    def __init__(
        self,
        message: str = "Appointments must be booked at least 1 hour in the future.",
    ) -> None:
        super().__init__(code="BOOKING_BUFFER_VIOLATION", message=message)


class OutsideWorkingHoursError(ValidationError):
    def __init__(
        self,
        message: str = "The appointment does not fit within the doctor's working hours for that day.",
    ) -> None:
        super().__init__(code="OUTSIDE_WORKING_HOURS", message=message)


class BlockedTimeOverlapError(ValidationError):
    def __init__(
        self,
        message: str = "The requested appointment overlaps with a doctor blocked time period.",
    ) -> None:
        super().__init__(code="BLOCKED_TIME_OVERLAP", message=message)


class InvalidDateError(ValidationError):
    def __init__(
        self,
        message: str = "Invalid date format or value.",
    ) -> None:
        super().__init__(code="INVALID_DATE", message=message)
