from datetime import datetime
from app.core.time_utils import CLINIC_TZ, get_current_time


def test_infra_fixtures(client, db, sample_doctor, sample_patient, freeze_clock):
    # Verify client
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

    # Verify doctor fixture
    assert sample_doctor.id is not None
    assert sample_doctor.is_active is True

    # Verify patient fixture
    assert sample_patient.id is not None

    # Verify clock freezing
    fixed = datetime(2026, 10, 26, 8, 0, 0, tzinfo=CLINIC_TZ)
    freeze_clock(fixed)
    assert get_current_time() == fixed
