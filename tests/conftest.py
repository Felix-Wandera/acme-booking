from datetime import datetime, time
from typing import Generator
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.time_utils import CLINIC_TZ, reset_system_time, set_system_time
from app.db.deps import get_db
from app.db.session import SessionLocal
from app.models.appointment import Appointment
from app.models.blocked_time import BlockedTime
from app.models.doctor import Doctor, DoctorWorkingHours
from app.models.patient import Patient
from main import app


@pytest.fixture(scope="session", autouse=True)
def ensure_clean_clock():
    """Ensure clock override is reset before and after the test session."""
    reset_system_time()
    yield
    reset_system_time()


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Provide a database session per test, ensuring rollback on exit."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient with get_db dependency overridden to the test session."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_doctor(db: Session) -> Generator[Doctor, None, None]:
    """
    Create an active doctor with standard Mon-Fri working hours:
    08:00 - 12:00 and 14:00 - 17:00 (EAT).
    Clean up upon test completion.
    """
    doc_id = uuid.uuid4()
    doctor = Doctor(
        id=doc_id,
        name="Dr. Test Fixture",
        is_active=True,
    )
    db.add(doctor)
    db.flush()

    # Add Mon-Fri working hours (days 0-4)
    for day in range(5):
        wh_morning = DoctorWorkingHours(
            doctor_id=doc_id,
            day_of_week=day,
            start_time=time(8, 0),
            end_time=time(12, 0),
        )
        wh_afternoon = DoctorWorkingHours(
            doctor_id=doc_id,
            day_of_week=day,
            start_time=time(14, 0),
            end_time=time(17, 0),
        )
        db.add_all([wh_morning, wh_afternoon])

    db.commit()

    yield doctor

    # Teardown in reverse dependency order
    db.execute(delete(Appointment).where(Appointment.doctor_id == doc_id))
    db.execute(delete(BlockedTime).where(BlockedTime.doctor_id == doc_id))
    db.execute(delete(DoctorWorkingHours).where(DoctorWorkingHours.doctor_id == doc_id))
    db.execute(delete(Doctor).where(Doctor.id == doc_id))
    db.commit()


@pytest.fixture
def sample_patient(db: Session) -> Generator[Patient, None, None]:
    """
    Create a test patient. Clean up upon test completion.
    """
    patient_id = uuid.uuid4()
    patient = Patient(
        id=patient_id,
        name="Test Patient Fixture",
        phone_number=f"+254700{str(patient_id.int)[:6]}",
    )
    db.add(patient)
    db.commit()

    yield patient

    db.execute(delete(Appointment).where(Appointment.patient_id == patient_id))
    db.execute(delete(Patient).where(Patient.id == patient_id))
    db.commit()


@pytest.fixture
def freeze_clock():
    """Fixture factory to freeze the system clock to a fixed datetime during a test."""
    def _freeze(frozen_dt: datetime):
        set_system_time(frozen_dt)

    yield _freeze
    reset_system_time()
