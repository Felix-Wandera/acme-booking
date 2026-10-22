from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import uuid
import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient

from app.core.exceptions import SlotUnavailableError
from app.core.time_utils import CLINIC_TZ
from app.db.session import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.patient import Patient
from app.services.booking_service import BookingService
from main import app


def test_concurrent_booking_race_condition_service_layer(sample_doctor, sample_patient, freeze_clock):
    """
    Test that 5 concurrent booking attempts for the exact same slot across 5 independent
    database connections result in strictly 1 success and 4 conflict rejections.
    Verifies that doctor row-level locking (SELECT ... FOR UPDATE) and the partial unique index
    (uq_active_appointment_per_slot) guarantee complete double-booking prevention.
    """
    target_slot = datetime(2026, 10, 26, 10, 0, tzinfo=CLINIC_TZ)
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))
    doc_id = sample_doctor.id  # Pass primitive UUID, not attached ORM object

    # Create 5 distinct patients so foreign key and patient identity are distinct
    patients = []
    with SessionLocal() as setup_db:
        for i in range(5):
            pat = Patient(
                id=uuid.uuid4(),
                name=f"Concurrent Patient {i}",
                phone_number=f"+25479900000{i}",
            )
            setup_db.add(pat)
            patients.append(pat.id)
        setup_db.commit()

    successes = []
    conflicts = []
    errors = []

    def attempt_booking(pat_id: uuid.UUID):
        # Dedicated independent DB connection and session per thread
        with SessionLocal() as thread_db:
            try:
                appt = BookingService.book_appointment(
                    db=thread_db,
                    doctor_id=doc_id,
                    patient_id=pat_id,
                    start_time=target_slot,
                )
                return ("SUCCESS", str(appt.id))
            except SlotUnavailableError as e:
                return ("CONFLICT", e.code)
            except Exception as e:
                return ("ERROR", str(e))

    # Fire 5 simultaneous booking requests
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(attempt_booking, pat_id) for pat_id in patients]
        for f in as_completed(futures):
            status_type, msg = f.result()
            if status_type == "SUCCESS":
                successes.append(msg)
            elif status_type == "CONFLICT":
                conflicts.append(msg)
            else:
                errors.append(msg)

    # Clean up created records
    with SessionLocal() as cleanup_db:
        cleanup_db.query(Appointment).filter(Appointment.doctor_id == doc_id).delete()
        cleanup_db.query(Patient).filter(Patient.id.in_(patients)).delete()
        cleanup_db.commit()

    # Assertions
    assert len(errors) == 0, f"Unexpected errors during concurrent booking: {errors}"
    assert len(successes) == 1, f"Expected exactly 1 successful booking, got {len(successes)}"
    assert len(conflicts) == 4, f"Expected exactly 4 conflict rejections, got {len(conflicts)}"
    for code in conflicts:
        assert code == "SLOT_UNAVAILABLE"


def test_concurrent_booking_race_condition_api_layer(sample_doctor, sample_patient, freeze_clock):
    """
    Test 5 concurrent HTTP requests to POST /appointments for the same slot.
    Asserts exactly one 201 Created and four 409 Conflict with SLOT_UNAVAILABLE.
    """
    target_slot = "2026-10-26T14:30:00+03:00"
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))
    doc_id_str = str(sample_doctor.id)  # Pass string UUID

    # Clear dependency overrides so each request gets its own independent SessionLocal
    app.dependency_overrides.clear()

    # Create 5 distinct patients
    patients = []
    with SessionLocal() as setup_db:
        for i in range(5):
            pat = Patient(
                id=uuid.uuid4(),
                name=f"Concurrent HTTP Patient {i}",
                phone_number=f"+25478800000{i}",
            )
            setup_db.add(pat)
            patients.append(str(pat.id))
        setup_db.commit()

    def send_booking_request(patient_id_str: str):
        # Dedicated TestClient per thread
        with TestClient(app) as thread_client:
            return thread_client.post("/appointments", json={
                "doctor_id": doc_id_str,
                "patient_id": patient_id_str,
                "start_time": target_slot,
            })

    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(send_booking_request, pat_id) for pat_id in patients]
        for f in as_completed(futures):
            results.append(f.result())

    # Clean up
    with SessionLocal() as cleanup_db:
        cleanup_db.query(Appointment).filter(Appointment.doctor_id == sample_doctor.id).delete()
        cleanup_db.query(Patient).filter(Patient.id.in_([uuid.UUID(p) for p in patients])).delete()
        cleanup_db.commit()

    status_codes = [r.status_code for r in results]
    assert status_codes.count(201) == 1, f"Expected 1x 201, got {status_codes}"
    assert status_codes.count(409) == 4, f"Expected 4x 409, got {status_codes}"

    for r in results:
        if r.status_code == 409:
            assert r.json()["detail"]["code"] == "SLOT_UNAVAILABLE"
