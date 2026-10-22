from fastapi import APIRouter

from app.api.v1.endpoints import appointments, doctors, patients

api_router = APIRouter()

api_router.include_router(
    appointments.router,
    prefix="/appointments",
    tags=["Appointments"],
)
api_router.include_router(
    doctors.router,
    prefix="/doctors",
    tags=["Doctors"],
)
api_router.include_router(
    patients.router,
    prefix="/patients",
    tags=["Patients"],
)
