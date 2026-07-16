from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod

@dataclass
class ScenarioConfig:
    """
    ScenarioConfig: The unified data structure for a simulation run.
    """
    location: str
    city_key: str
    scenario_id: str
    srid: int
    osm_input: str
    od_input: str
    census_input: str
    ciclo_input: Optional[str] = None
    projects_input: Optional[str] = None
    reference_scenario: Optional[str] = None
    bbox: Optional[List[float]] = None
    
    # Magnetism & Topology Parameters (Phase 18)
    mr_distance: float = 5.0
    ma_distance: float = 7.0
    zp_distance: float = 25.0
    
    # Impedance Parameters
    buffer_size: int = 15
    imp_primary: float = 10.0
    imp_secondary: float = 5.0
    imp_tertiary: float = 2.0
    imp_local: float = 1.0
    imp_bike: float = 0.8
    
    # Flags
    inhibit: bool = True
    disinhibit: bool = True
    cleanup: bool = False
    mapping: bool = True

class ProgressSeam(ABC):
    """
    ProgressSeam: Abstract interface for emitting pipeline progress and telemetry.
    """
    @abstractmethod
    def on_stage_start(self, stage_id: int, name: str, eta: str = "Auto"):
        pass

    @abstractmethod
    def on_stage_end(self, stage_id: int, success: bool = True):
        pass

    @abstractmethod
    def on_progress_update(self, status: str, increment: int = 1, total: Optional[int] = None):
        pass

    @abstractmethod
    def report_diagnostic(self, tag: str, level: str, message: str):
        pass

    @abstractmethod
    def get_timings(self) -> Dict[str, float]:
        """Retrieve collected stage timings for telemetry."""
        pass

@dataclass
class ScenarioContext:
    """
    ScenarioContext: The shared state container for the pipeline.
    Provides locality for table naming and database connection management.
    """
    config: ScenarioConfig
    conn: Any
    observer: ProgressSeam
    db_config: Dict[str, Any] = field(default_factory=dict)
    tables: Dict[str, str] = field(default_factory=dict)
    state: Dict[str, Any] = field(default_factory=dict)
    
    def get_table(self, key: str) -> str:
        """Centralized table name resolution to eliminate string coupling."""
        return self.tables.get(key, f"unknown_{key}")

class PipelineTask(ABC):
    """
    PipelineTask: Abstract interface for simulation stages.
    """
    @property
    @abstractmethod
    def stage_id(self) -> int:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def execute(self, context: ScenarioContext) -> None:
        """Execute the task logic behind the seam."""
        pass

    def rollback(self, context: ScenarioContext) -> None:
        """Optional rollback logic for transactional resilience."""
        pass

class ScenarioPipeline:
    """
    ScenarioPipeline: The orchestrator that manages task execution and telemetry.
    """
    def __init__(self, context: ScenarioContext):
        self.context = context
        self.tasks: list[PipelineTask] = []

    def add_task(self, task: PipelineTask):
        self.tasks.append(task)

    def execute(self):
        self.context.observer.report_diagnostic("PIPELINE", "INFO", f"Starting pipeline for {self.context.config.location}...")
        
        for task in self.tasks:
            try:
                self.context.observer.on_stage_start(task.stage_id, task.name)
                task.execute(self.context)
                self.context.observer.on_stage_end(task.stage_id, True)
            except Exception as e:
                self.context.observer.on_stage_end(task.stage_id, False)
                self.context.observer.report_diagnostic("TASK_FAILURE", "ERROR", f"Task {task.name} failed: {str(e)}")
                task.rollback(self.context)
                raise e
        
        self.context.observer.report_diagnostic("PIPELINE", "INFO", "Pipeline completed successfully.")
