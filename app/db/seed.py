from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time_utils import CLINIC_TZ, get_current_time
from app.models.appointment import Appointment, AppointmentStatus
from app.models.blocked_time import BlockedTime
from app.models.doctor import Doctor, DoctorWorkingHours
from app.models.patient import Patient

# Deterministic UUIDs for predictable evaluation and testing
DOCTOR_IDS = {
    "dr_kamau": uuid.UUID("11111111-1111-1111-1111-111111111111"),
    "dr_ochieng": uuid.UUID("22222222-2222-2222-2222-222222222222"),
    "dr_mutua": uuid.UUID("33333333-3333-3333-3333-333333333333"),
    "dr_kiprop": uuid.UUID("44444444-4444-4444-4444-444444444444"),
    "dr_wanjiku": uuid.UUID("55555555-5555-5555-5555-555555555555"),
}

PATIENT_IDS = {
    "john_mwangi": uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    "sarah_chebet": uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
    "daniel_otieno": uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
}

# 5 Clinic Doctors with realistic shifts
CLINIC_DOCTORS = [
    {
        "id": DOCTOR_IDS["dr_kamau"],
        "name": "Dr. Aisha Kamau (General Practice)",
        "is_active": True,
        # Mon-Fri: 08:00 - 12:00, 14:00 - 17:00
        "schedules": [
            {"days": [0, 1, 2, 3, 4], "start": time(8, 0), "end": time(12, 0)},
            {"days": [0, 1, 2, 3, 4], "start": time(14, 0), "end": time(17, 0)},
        ],
    },
    {
        "id": DOCTOR_IDS["dr_ochieng"],
        "name": "Dr. Brian Ochieng (Cardiology)",
        "is_active": True,
        # Mon, Wed, Fri: 08:30 - 12:30, 14:00 - 16:30
        "schedules": [
            {"days": [0, 2, 4], "start": time(8, 30), "end": time(12, 30)},
            {"days": [0, 2, 4], "start": time(14, 0), "end": time(16, 30)},
        ],
    },
    {
        "id": DOCTOR_IDS["dr_mutua"],
        "name": "Dr. Catherine Mutua (Pediatrics)",
        "is_active": True,
        # Mon-Thu: 09:00 - 13:00, 14:00 - 17:00
        "schedules": [
            {"days": [0, 1, 2, 3], "start": time(9, 0), "end": time(13, 0)},
            {"days": [0, 1, 2, 3], "start": time(14, 0), "end": time(17, 0)},
        ],
    },
    {
        "id": DOCTOR_IDS["dr_kiprop"],
        "name": "Dr. David Kiprop (Orthopedics)",
        "is_active": True,
        # Tue, Thu, Sat: 08:00 - 12:00, 13:30 - 16:30
        "schedules": [
            {"days": [1, 3, 5], "start": time(8, 0), "end": time(12, 0)},
            {"days": [1, 3, 5], "start": time(13, 30), "end": time(16, 30)},
        ],
    },
    {
        "id": DOCTOR_IDS["dr_wanjiku"],
        "name": "Dr. Elena Wanjiku (Dermatology)",
        "is_active": True,
        # Mon-Fri: 09:00 - 12:00, 13:00 - 16:00
        "schedules": [
            {"days": [0, 1, 2, 3, 4], "start": time(9, 0), "end": time(12, 0)},
            {"days": [0, 1, 2, 3, 4], "start": time(13, 0), "end": time(16, 0)},
        ],
    },
]

CLINIC_PATIENTS = [
    {
        "id": PATIENT_IDS["john_mwangi"],
        "name": "John Mwangi",
        "phone_number": "+254711000001",
    },
    {
        "id": PATIENT_IDS["sarah_chebet"],
        "name": "Sarah Chebet",
        "phone_number": "+254722000002",
    },
    {
        "id": PATIENT_IDS["daniel_otieno"],
        "name": "Daniel Otieno",
        "phone_number": "+254733000003",
    },
]


def get_next_clinic_weekday(start_dt: datetime) -> date:
    """Find the next Monday–Friday calendar date at least 1 day in the future."""
    candidate = start_dt.date() + timedelta(days=1)
    while candidate.weekday() > 4:  # Saturday or Sunday
        candidate += timedelta(days=1)
    return candidate


def reset_database(db: Session, force: bool = False) -> None:
    """
    Safely delete all clinic records in reverse foreign-key order.
    Guarded against accidental execution in production.
    """
    env = getattr(settings, "ENVIRONMENT", "development").lower()
    if env == "production" and not force:
        raise RuntimeError("Refusing to reset database in production environment without explicit force flag.")

    # Strictly reverse foreign-key order
    db.execute(delete(Appointment))
    db.execute(delete(BlockedTime))
    db.execute(delete(DoctorWorkingHours))
    db.execute(delete(Patient))
    db.execute(delete(Doctor))
    db.commit()


def seed_database(db: Session, reset: bool = False, force: bool = False) -> Dict[str, Any]:
    """
    Seed Acme Hospital Clinic database with 5 doctors, schedules, patients, and sample appointments.
    Strictly idempotent: will not create duplicate records on repeated executions.
    """
    if reset:
        reset_database(db, force=force)

    stats = {
        "doctors_created": 0,
        "working_hours_created": 0,
        "patients_created": 0,
        "blocked_times_created": 0,
        "appointments_created": 0,
    }

    # 1. Seed Doctors & Schedules
    for doc_data in CLINIC_DOCTORS:
        doctor = db.get(Doctor, doc_data["id"])
        if not doctor:
            doctor = Doctor(
                id=doc_data["id"],
                name=doc_data["name"],
                is_active=doc_data["is_active"],
            )
            db.add(doctor)
            db.flush()
            stats["doctors_created"] += 1

            for schedule in doc_data["schedules"]:
                for day in schedule["days"]:
                    wh = DoctorWorkingHours(
                        doctor_id=doctor.id,
                        day_of_week=day,
                        start_time=schedule["start"],
                        end_time=schedule["end"],
                    )
                    db.add(wh)
                    stats["working_hours_created"] += 1

    # 2. Seed Patients
    for pat_data in CLINIC_PATIENTS:
        patient = db.get(Patient, pat_data["id"])
        if not patient:
            patient = Patient(
                id=pat_data["id"],
                name=pat_data["name"],
                phone_number=pat_data["phone_number"],
            )
            db.add(patient)
            stats["patients_created"] += 1

    db.commit()

    # 3. Seed Sample Blocked Period (Upcoming clinic staff meeting)
    now = get_current_time()
    next_clinic_day = get_next_clinic_weekday(now)

    # Add lunch block on next clinic day (12:00 - 14:00) for Dr. Kamau if none exists
    sample_block_start = datetime.combine(next_clinic_day, time(12, 0), tzinfo=CLINIC_TZ)
    sample_block_end = datetime.combine(next_clinic_day, time(14, 0), tzinfo=CLINIC_TZ)

    existing_block = db.scalars(
        select(BlockedTime).where(
            BlockedTime.doctor_id == DOCTOR_IDS["dr_kamau"],
            BlockedTime.start_time == sample_block_start,
        )
    ).first()

    if not existing_block:
        bt = BlockedTime(
            doctor_id=DOCTOR_IDS["dr_kamau"],
            start_time=sample_block_start,
            end_time=sample_block_end,
            reason="Clinical Staff Meeting & Lunch",
        )
        db.add(bt)
        stats["blocked_times_created"] += 1

    # 4. Seed Sample Active Appointment (For testing availability & upcoming appointments)
    # Next clinic day at 10:00 for Dr. Kamau and John Mwangi
    sample_appt_start = datetime.combine(next_clinic_day, time(10, 0), tzinfo=CLINIC_TZ)

    existing_appt = db.scalars(
        select(Appointment).where(
            Appointment.doctor_id == DOCTOR_IDS["dr_kamau"],
            Appointment.start_time == sample_appt_start,
            Appointment.status == AppointmentStatus.BOOKED,
        )
    ).first()

    if not existing_appt:
        appt = Appointment(
            doctor_id=DOCTOR_IDS["dr_kamau"],
            patient_id=PATIENT_IDS["john_mwangi"],
            start_time=sample_appt_start,
            status=AppointmentStatus.BOOKED,
        )
        db.add(appt)
        stats["appointments_created"] += 1

    db.commit()

    return {
        "stats": stats,
        "sample_date": str(next_clinic_day),
        "doctors": [
            {"id": str(d["id"]), "name": d["name"]} for d in CLINIC_DOCTORS
        ],
        "patients": [
            {"id": str(p["id"]), "name": p["name"], "phone": p["phone_number"]}
            for p in CLINIC_PATIENTS
        ],
    }
