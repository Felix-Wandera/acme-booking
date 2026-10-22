from datetime import date, datetime, time, timedelta
import uuid
import pytest
from app.core.time_utils import CLINIC_TZ
from app.models.appointment import Appointment, AppointmentStatus
from app.models.blocked_time import BlockedTime


def test_availability_returns_ordered_slots(client, sample_doctor, freeze_clock):
    # Monday 2026-10-26 at 06:00 (well before shift starts)
    freeze_clock(datetime(2026, 10, 26, 6, 0, tzinfo=CLINIC_TZ))

    response = client.get(f"/doctors/{sample_doctor.id}/availability?date=2026-10-26")
    assert response.status_code == 200
    data = response.json()

    assert data["doctor_id"] == str(sample_doctor.id)
    assert data["date"] == "2026-10-26"
    assert data["timezone"] == "Africa/Nairobi"

    slots = data["available_slots"]
    # 08:00-12:00 (8 slots) + 14:00-17:00 (6 slots) = 14 slots
    assert len(slots) == 14

    # Verify ascending chronological order
    datetimes = [datetime.fromisoformat(s) for s in slots]
    assert datetimes == sorted(datetimes)

    # First and last slots
    assert slots[0] == "2026-10-26T08:00:00+03:00"
    assert slots[-1] == "2026-10-26T16:30:00+03:00"


def test_availability_excludes_booked_slots(client, db, sample_doctor, sample_patient, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 6, 0, tzinfo=CLINIC_TZ))

    # Book 09:00 slot
    booked_dt = datetime(2026, 10, 26, 9, 0, tzinfo=CLINIC_TZ)
    appt = Appointment(
        doctor_id=sample_doctor.id,
        patient_id=sample_patient.id,
        start_time=booked_dt,
        status=AppointmentStatus.BOOKED,
    )
    db.add(appt)
    db.commit()

    response = client.get(f"/doctors/{sample_doctor.id}/availability?date=2026-10-26")
    assert response.status_code == 200
    slots = response.json()["available_slots"]

    assert "2026-10-26T09:00:00+03:00" not in slots
    assert "2026-10-26T08:30:00+03:00" in slots
    assert "2026-10-26T09:30:00+03:00" in slots
    assert len(slots) == 13


def test_availability_excludes_blocked_periods(client, db, sample_doctor, freeze_clock):
    freeze_clock(datetime(2026, 10, 26, 6, 0, tzinfo=CLINIC_TZ))

    # Block 10:00 to 11:00 (affects 10:00 and 10:30)
    bt = BlockedTime(
        doctor_id=sample_doctor.id,
        start_time=datetime(2026, 10, 26, 10, 0, tzinfo=CLINIC_TZ),
        end_time=datetime(2026, 10, 26, 11, 0, tzinfo=CLINIC_TZ),
        reason="Department Meeting",
    )
    db.add(bt)
    db.commit()

    response = client.get(f"/doctors/{sample_doctor.id}/availability?date=2026-10-26")
    assert response.status_code == 200
    slots = response.json()["available_slots"]

    assert "2026-10-26T10:00:00+03:00" not in slots
    assert "2026-10-26T10:30:00+03:00" not in slots
    assert "2026-10-26T09:30:00+03:00" in slots
    assert "2026-10-26T11:00:00+03:00" in slots


def test_availability_excludes_past_and_buffer_slots(client, sample_doctor, freeze_clock):
    # Set current time to Monday 09:45 EAT
    freeze_clock(datetime(2026, 10, 26, 9, 45, tzinfo=CLINIC_TZ))

    response = client.get(f"/doctors/{sample_doctor.id}/availability?date=2026-10-26")
    assert response.status_code == 200
    slots = response.json()["available_slots"]

    # Current time = 09:45, 1-hour buffer cutoff = 10:45.
    # Slots <= 10:45 (08:00, 08:30, 09:00, 09:30, 10:00, 10:30) must be excluded.
    for slot in ["08:00", "08:30", "09:00", "09:30", "10:00", "10:30"]:
        assert f"2026-10-26T{slot}:00+03:00" not in slots

    # First morning slot available after cutoff
    assert "2026-10-26T11:00:00+03:00" in slots


def test_availability_empty_on_non_working_days(client, sample_doctor, freeze_clock):
    freeze_clock(datetime(2026, 10, 25, 6, 0, tzinfo=CLINIC_TZ))

    # 2026-10-25 is Sunday (sample doctor only works Mon-Fri)
    response = client.get(f"/doctors/{sample_doctor.id}/availability?date=2026-10-25")
    assert response.status_code == 200
    assert response.json()["available_slots"] == []


def test_availability_doctor_not_found(client):
    fake_id = uuid.uuid4()
    response = client.get(f"/doctors/{fake_id}/availability?date=2026-10-26")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "DOCTOR_NOT_FOUND"


def test_availability_invalid_date_format(client, sample_doctor):
    response = client.get(f"/doctors/{sample_doctor.id}/availability?date=2026-13-45")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_DATE"
