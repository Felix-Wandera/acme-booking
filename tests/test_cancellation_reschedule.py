from datetime import datetime
import uuid
import pytest
from app.core.time_utils import CLINIC_TZ
from app.models.appointment import Appointment, AppointmentStatus


def test_successful_cancellation(client, sample_doctor, sample_patient, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    # Book appointment
    booking = client.post("/appointments", json={
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:00:00+03:00",
    }).json()

    appt_id = booking["id"]

    # Cancel appointment
    response = client.patch(f"/appointments/{appt_id}/cancel", json={
        "reason": "Patient feeling much better",
    })
    assert response.status_code == 200
    data = response.json()

    assert data["id"] == appt_id
    assert data["status"] == "CANCELLED"
    assert data["cancellation_reason"] == "Patient feeling much better"


def test_cancelled_slot_becomes_bookable_again(client, sample_doctor, sample_patient, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    # Patient 1 books 10:00
    booking1 = client.post("/appointments", json={
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:00:00+03:00",
    }).json()

    # Cancel booking 1
    client.patch(f"/appointments/{booking1['id']}/cancel", json={
        "reason": "Cancelled",
    })

    # Patient 2 books 10:00 -> must succeed with 201
    second_patient_id = uuid.uuid4()
    # Create patient 2
    r_book2 = client.post("/appointments", json={
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:00:00+03:00",
    })
    assert r_book2.status_code == 201
    assert r_book2.json()["status"] == "BOOKED"


def test_repeated_cancellation_returns_conflict(client, sample_doctor, sample_patient, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    booking = client.post("/appointments", json={
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:00:00+03:00",
    }).json()
    appt_id = booking["id"]

    # First cancel -> 200
    r1 = client.patch(f"/appointments/{appt_id}/cancel", json={"reason": "First cancel"})
    assert r1.status_code == 200

    # Second cancel -> 409 Conflict
    r2 = client.patch(f"/appointments/{appt_id}/cancel", json={"reason": "Second cancel"})
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == "APPOINTMENT_ALREADY_CANCELLED"


def test_past_appointment_cannot_be_cancelled(client, sample_doctor, sample_patient, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    booking = client.post("/appointments", json={
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:00:00+03:00",
    }).json()

    # Fast forward time to 10:30 (appointment has started/passed)
    freeze_clock(datetime(2026, 10, 26, 10, 30, tzinfo=CLINIC_TZ))

    response = client.patch(f"/appointments/{booking['id']}/cancel", json={"reason": "Too late"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "APPOINTMENT_ALREADY_STARTED"


def test_cancellation_missing_reason(client, sample_doctor, sample_patient, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    booking = client.post("/appointments", json={
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:00:00+03:00",
    }).json()

    response = client.patch(f"/appointments/{booking['id']}/cancel", json={"reason": "   "})
    assert response.status_code in (400, 422)
    assert response.json()["detail"]["code"] in ("INVALID_CANCELLATION_REASON", "VALIDATION_ERROR")


def test_successful_reschedule(client, sample_doctor, sample_patient, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    booking = client.post("/appointments", json={
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:00:00+03:00",
    }).json()
    appt_id = booking["id"]

    # Reschedule to 11:00
    response = client.patch(f"/appointments/{appt_id}/reschedule", json={
        "new_start_time": "2026-10-26T11:00:00+03:00",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == appt_id
    assert data["start_time"] == "2026-10-26T11:00:00+03:00"

    # Freed 10:00 slot can now be booked
    r_old = client.post("/appointments", json={
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:00:00+03:00",
    })
    assert r_old.status_code == 201


def test_reschedule_conflict_on_taken_slot(client, db, sample_doctor, sample_patient, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    # Appt 1 at 10:00
    appt1 = client.post("/appointments", json={
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:00:00+03:00",
    }).json()

    # Appt 2 at 11:00
    appt2 = client.post("/appointments", json={
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T11:00:00+03:00",
    }).json()

    # Try moving appt1 to 11:00 -> 409 Conflict
    response = client.patch(f"/appointments/{appt1['id']}/reschedule", json={
        "new_start_time": "2026-10-26T11:00:00+03:00",
    })
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SLOT_UNAVAILABLE"

    # Check that appt1 remains untouched at 10:00 in DB
    db.expire_all()
    record = db.get(Appointment, uuid.UUID(appt1["id"]))
    assert record.start_time.astimezone(CLINIC_TZ).strftime("%H:%M") == "10:00"


def test_reschedule_cancelled_appointment_returns_conflict(client, sample_doctor, sample_patient, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    booking = client.post("/appointments", json={
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:00:00+03:00",
    }).json()

    # Cancel
    client.patch(f"/appointments/{booking['id']}/cancel", json={"reason": "Cancel"})

    # Reschedule cancelled appointment -> 409
    response = client.patch(f"/appointments/{booking['id']}/reschedule", json={
        "new_start_time": "2026-10-26T11:00:00+03:00",
    })
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "APPOINTMENT_ALREADY_CANCELLED"
