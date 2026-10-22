from datetime import datetime, timedelta
import uuid
import pytest
from app.core.time_utils import CLINIC_TZ
from app.models.appointment import Appointment
from app.models.blocked_time import BlockedTime


def test_successful_booking(client, sample_doctor, sample_patient, freeze_clock):
    # Freeze time at Monday 08:00
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    payload = {
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:00:00+03:00",
    }
    response = client.post("/appointments", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["doctor_id"] == str(sample_doctor.id)
    assert data["patient_id"] == str(sample_patient.id)
    assert data["start_time"] == "2026-10-26T10:00:00+03:00"
    assert data["status"] == "BOOKED"
    assert data["cancellation_reason"] is None
    assert "id" in data


def test_booking_rejection_outside_working_hours(client, sample_doctor, sample_patient, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    # Shift ends at 17:00, 18:00 is outside
    payload = {
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T18:00:00+03:00",
    }
    response = client.post("/appointments", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "OUTSIDE_WORKING_HOURS"


def test_booking_rejection_invalid_slot_alignment(client, sample_doctor, sample_patient, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    # 10:15 is not aligned to 30-minute boundary
    payload = {
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:15:00+03:00",
    }
    response = client.post("/appointments", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_SLOT_ALIGNMENT"


def test_booking_rejection_buffer_violation(client, sample_doctor, sample_patient, freeze_clock):
    # Set time to 09:15, attempt booking 10:00 (only 45 mins ahead < 1 hour)
    freeze_clock(datetime(2026, 10, 26, 9, 15, tzinfo=CLINIC_TZ))

    payload = {
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:00:00+03:00",
    }
    response = client.post("/appointments", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "BOOKING_BUFFER_VIOLATION"


def test_booking_rejection_blocked_time_overlap(client, db, sample_doctor, sample_patient, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    # Block 11:00 - 12:00
    bt = BlockedTime(
        doctor_id=sample_doctor.id,
        start_time=datetime(2026, 10, 26, 11, 0, tzinfo=CLINIC_TZ),
        end_time=datetime(2026, 10, 26, 12, 0, tzinfo=CLINIC_TZ),
        reason="Doctor Leave",
    )
    db.add(bt)
    db.commit()

    payload = {
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T11:30:00+03:00",
    }
    response = client.post("/appointments", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "BLOCKED_TIME_OVERLAP"


def test_booking_rejection_duplicate_booking(client, sample_doctor, sample_patient, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    payload = {
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:00:00+03:00",
    }
    # First booking succeeds
    r1 = client.post("/appointments", json=payload)
    assert r1.status_code == 201

    # Second booking fails with 409
    r2 = client.post("/appointments", json=payload)
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == "SLOT_UNAVAILABLE"


def test_booking_rejection_non_existent_entities(client, sample_doctor, sample_patient, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    # Fake doctor
    r1 = client.post("/appointments", json={
        "doctor_id": str(uuid.uuid4()),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:00:00+03:00",
    })
    assert r1.status_code == 404
    assert r1.json()["detail"]["code"] == "DOCTOR_NOT_FOUND"

    # Fake patient
    r2 = client.post("/appointments", json={
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(uuid.uuid4()),
        "start_time": "2026-10-26T10:00:00+03:00",
    })
    assert r2.status_code == 404
    assert r2.json()["detail"]["code"] == "PATIENT_NOT_FOUND"


def test_booking_rejection_inactive_doctor(client, db, sample_doctor, sample_patient, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    sample_doctor.is_active = False
    db.commit()

    payload = {
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:00:00+03:00",
    }
    response = client.post("/appointments", json=payload)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DOCTOR_INACTIVE"
