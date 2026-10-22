from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Structured error detail containing a machine-readable code and human-readable message."""
    code: str = Field(..., examples=["SLOT_UNAVAILABLE"])
    message: str = Field(..., examples=["The selected slot is no longer available."])


class ErrorResponse(BaseModel):
    """Uniform error response shape across all endpoints."""
    detail: ErrorDetail
