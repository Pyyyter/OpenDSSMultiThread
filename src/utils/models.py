"""Domain Models for OpenDSS MultiThread."""
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any


@dataclass
class VariableSpec:
    """Specification for a numeric variable extracted from DSS files."""

    id: str
    name: str
    value: float
    line: int
    kind: str  # "key_value" or "line_value"
    relative_path: str
    match_index: int
    threshold_pct: float = 0.0  # Randomization threshold


@dataclass
class RandomizationRule:
    """Rule for randomizing a variable."""

    variable_id: str
    base_value: float
    limit_pct: float
    linked_group: Optional[str] = None


@dataclass
class MonitorLimit:
    """Safety limits for a monitor."""

    monitor_name: str
    target: float
    offset: float

    @property
    def lower_bound(self) -> float:
        return self.target - self.offset

    @property
    def upper_bound(self) -> float:
        return self.target + self.offset

    def is_violation(self, value: float) -> bool:
        """Check if value violates the limits."""
        return value < self.lower_bound or value > self.upper_bound


@dataclass
class SimulationCase:
    """Specification for a case to execute."""

    case_index: int
    scenario_dir: str
    seed: int
    main_file: str


@dataclass
class MonitorDataset:
    """Data from a monitor (columns + rows)."""

    columns: List[str]
    rows: List[List[Any]]


@dataclass
class CaseResult:
    """Result from executing a single case."""

    case: int
    data: Optional[Dict[str, MonitorDataset]] = None
    monitors: List[str] = field(default_factory=list)
    scenario_dir: Optional[str] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None

    @property
    def failed(self) -> bool:
        return self.error is not None


@dataclass
class ExecutionStats:
    """Statistics from an execution run."""

    case_count: int
    total_time: float
    workers_used: int
    success_count: int
    error_count: int

    @property
    def success_rate(self) -> float:
        return self.success_count / self.case_count if self.case_count > 0 else 0.0
