from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict


class BlockedTimeResponse(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    start_time: datetime
    end_time: datetime
    reason: str

    model_config = ConfigDict(from_attributes=True)
