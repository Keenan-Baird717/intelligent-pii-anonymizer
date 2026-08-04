from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(description="Overall API status: ok or degraded")
    database: str = Field(description="Database connectivity: connected or unavailable")
    version: str = Field(description="API version identifier")
