from datetime import datetime, timedelta
import uuid
import pytest
from app.core.time_utils import CLINIC_TZ
from app.models.appointment import Appointment, AppointmentStatus


def test_patient_upcoming_appointments_chronological(client, sample_doctor, sample_patient, freeze_clock):
    # Freeze time Monday 08:00
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    # Book 1st: Monday 11:00
    client.post("/appointments", json={
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T11:00:00+03:00",
    })

    # Book 2nd: Monday 10:00
    client.post("/appointments", json={
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:00:00+03:00",
    })

    response = client.get(f"/patients/{sample_patient.id}/appointments")
    assert response.status_code == 200
    appts = response.json()

    assert len(appts) == 2
    # Chronological sort: 10:00 must come before 11:00
    assert appts[0]["start_time"] == "2026-10-26T10:00:00+03:00"
    assert appts[1]["start_time"] == "2026-10-26T11:00:00+03:00"


def test_patient_upcoming_excludes_cancelled_and_past(client, db, sample_doctor, sample_patient, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    # Active upcoming appointment (10:00)
    appt_upcoming = client.post("/appointments", json={
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T10:00:00+03:00",
    }).json()

    # Cancelled appointment (11:00)
    appt_cancelled = client.post("/appointments", json={
        "doctor_id": str(sample_doctor.id),
        "patient_id": str(sample_patient.id),
        "start_time": "2026-10-26T11:00:00+03:00",
    }).json()
    client.patch(f"/appointments/{appt_cancelled['id']}/cancel", json={"reason": "Cancel"})

    # Past appointment (07:00) directly inserted
    past_appt = Appointment(
        doctor_id=sample_doctor.id,
        patient_id=sample_patient.id,
        start_time=datetime(2026, 10, 26, 7, 0, tzinfo=CLINIC_TZ),
        status=AppointmentStatus.BOOKED,
    )
    db.add(past_appt)
    db.commit()

    response = client.get(f"/patients/{sample_patient.id}/appointments")
    assert response.status_code == 200
    appts = response.json()

    # Only 10:00 should be returned
    assert len(appts) == 1
    assert appts[0]["id"] == appt_upcoming["id"]


def test_patient_upcoming_pagination(client, sample_doctor, sample_patient, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 8, 0, tzinfo=CLINIC_TZ))

    # Book 3 slots: 10:00, 10:30, 11:00
    for slot in ["10:00", "10:30", "11:00"]:
        client.post("/appointments", json={
            "doctor_id": str(sample_doctor.id),
            "patient_id": str(sample_patient.id),
            "start_time": f"2026-10-26T{slot}:00+03:00",
        })

    # Page 1 (limit 2, offset 0)
    r1 = client.get(f"/patients/{sample_patient.id}/appointments?limit=2&offset=0")
    assert r1.status_code == 200
    p1 = r1.json()
    assert len(p1) == 2
    assert p1[0]["start_time"] == "2026-10-26T10:00:00+03:00"
    assert p1[1]["start_time"] == "2026-10-26T10:30:00+03:00"

    # Page 2 (limit 2, offset 2)
    r2 = client.get(f"/patients/{sample_patient.id}/appointments?limit=2&offset=2")
    assert r2.status_code == 200
    p2 = r2.json()
    assert len(p2) == 1
    assert p2[0]["start_time"] == "2026-10-26T11:00:00+03:00"


def test_patient_not_found(client):
    fake_id = uuid.uuid4()
    response = client.get(f"/patients/{fake_id}/appointments")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PATIENT_NOT_FOUND"
