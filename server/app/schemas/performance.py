"""Performance measurement, baseline calculation, and regression analytics schemas."""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

from app.schemas.run import EnvironmentInfo


class RegressionStatus(str, Enum):
    """Classification of command execution duration relative to established baseline."""

    UNKNOWN = "unknown"
    NORMAL = "normal"
    POTENTIAL_REGRESSION = "potential_regression"


class PerformanceMeasurementCreate(BaseModel):
    """Payload for recording a command execution performance measurement."""

    event_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Stable reference to command-run event ID",
    )
    project_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Project identifier",
    )
    command: Optional[str] = Field(
        default=None,
        max_length=4096,
        description="Executed command string (inferred from referenced run if omitted)",
    )
    command_signature: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Normalized command signature (computed if omitted)",
    )
    command_label: Optional[str] = Field(
        default=None,
        max_length=256,
        description="Sanitized display label (computed if omitted)",
    )
    duration_ms: Optional[int] = Field(
        default=None,
        ge=0,
        description="Execution duration in milliseconds (inferred from run if omitted)",
    )
    exit_code: Optional[int] = Field(
        default=None,
        description="Process exit code (inferred from run if omitted)",
    )
    timestamp: Optional[datetime] = Field(
        default=None,
        description="Timestamp of execution (inferred from run if omitted)",
    )
    environment: Optional[EnvironmentInfo] = Field(
        default=None,
        description="Execution environment metadata",
    )


class PerformanceMeasurementResponse(BaseModel):
    """Persisted performance measurement record."""

    event_id: str
    project_id: str
    command_signature: str
    command_label: str
    duration_ms: int
    exit_code: int
    timestamp: datetime
    environment: Optional[EnvironmentInfo] = None
    baseline_duration_ms: Optional[float] = None
    regression_status: RegressionStatus = RegressionStatus.UNKNOWN
    created_at: datetime
    idempotent: bool = False


class BaselineCalculationRequest(BaseModel):
    """Optional parameters for computing project performance baselines."""

    command_signature: Optional[str] = Field(
        default=None,
        description="Target command signature; if omitted, calculates for all signatures in project",
    )
    min_samples: Optional[int] = Field(
        default=None,
        ge=1,
        description="Minimum sample count threshold override",
    )


class PerformanceBaselineResponse(BaseModel):
    """Established performance baseline for a comparable command signature."""

    project_id: str
    command_signature: str
    command_label: str
    baseline_duration_ms: Optional[float] = None
    sample_count: int = Field(ge=0)
    min_samples_required: int = Field(default=5, ge=1)
    status: str = Field(description="'established' or 'insufficient_data'")
    metric: str = "median"
    min_duration_ms: Optional[float] = None
    max_duration_ms: Optional[float] = None
    mean_duration_ms: Optional[float] = None
    calculated_at: datetime
    message: Optional[str] = None


class CommandPerformanceSummary(BaseModel):
    """Summary performance metrics for a specific command signature."""

    command_signature: str
    command_label: str
    total_runs: int = Field(ge=0)
    successful_runs: int = Field(ge=0)
    failed_runs: int = Field(ge=0)
    average_duration_ms: Optional[float] = Field(default=None, ge=0)
    median_duration_ms: Optional[float] = Field(default=None, ge=0)
    min_duration_ms: Optional[float] = Field(default=None, ge=0)
    max_duration_ms: Optional[float] = Field(default=None, ge=0)
    potential_regressions_count: int = Field(ge=0, default=0)
    baseline_duration_ms: Optional[float] = Field(default=None, ge=0)
    latest_duration_ms: Optional[float] = Field(default=None, ge=0)
    latest_run_at: Optional[datetime] = None


class PerformanceAnalyticsResponse(BaseModel):
    """Project-wide performance summary and command-grouped analytics."""

    project_id: str
    total_measurements: int = Field(ge=0)
    successful_measurements: int = Field(ge=0)
    failed_measurements: int = Field(ge=0)
    average_duration_ms: Optional[float] = Field(default=None, ge=0)
    median_duration_ms: Optional[float] = Field(default=None, ge=0)
    potential_regressions_count: int = Field(ge=0, default=0)
    latest_measurement_at: Optional[datetime] = None
    commands: List[CommandPerformanceSummary] = Field(default_factory=list)
