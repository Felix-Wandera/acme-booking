from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.api.errors import setup_exception_handlers
from app.api.v1.api import api_router
from app.core.config import settings

# OpenAPI Tags metadata
tags_metadata = [
    {
        "name": "Appointments",
        "description": "Appointment booking, cancellation, and rescheduling operations.",
    },
    {
        "name": "Doctors",
        "description": "Doctor queries and 30-minute availability calculations.",
    },
    {
        "name": "Patients",
        "description": "Patient management and upcoming appointment queries.",
    },
    {
        "name": "Health",
        "description": "System health and status verification endpoints.",
    },
]

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    version=settings.VERSION,
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register structured global exception handlers
setup_exception_handlers(app)

# Mount API v1 router with both /api/v1 and root prefixes for flexible URL access
app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(api_router)


@app.get(
    "/",
    tags=["Health"],
    status_code=status.HTTP_200_OK,
    summary="Root API info",
)
def read_root():
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "online",
        "timezone": settings.TIMEZONE,
        "docs_url": "/docs",
    }


@app.get(
    "/health",
    tags=["Health"],
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint",
)
def health_check():
    return {
        "status": "healthy",
        "timezone": settings.TIMEZONE,
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
