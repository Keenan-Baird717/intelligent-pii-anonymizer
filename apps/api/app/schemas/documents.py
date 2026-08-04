from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobMetadataResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    job_id: UUID
    status: str
    file_type: str
    byte_size: int = Field(ge=0)
    page_count: int | None = Field(default=None, ge=0)
    image_width: int | None = Field(default=None, ge=0)
    image_height: int | None = Field(default=None, ge=0)
    created_at: datetime
    expires_at: datetime
    error_code: str | None = Field(default=None, description="Safe failure code when applicable")


class DeleteJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    deleted: bool = True
