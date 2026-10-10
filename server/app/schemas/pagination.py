"""Pagination models for list endpoints."""

from typing import Generic, List, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standardized paginated list wrapper."""

    items: List[T] = Field(description="List of records for the requested page")
    total: int = Field(ge=0, description="Total number of matching records in the collection")
    limit: int = Field(ge=1, description="Page size limit applied")
    skip: int = Field(ge=0, description="Number of skipped records")
