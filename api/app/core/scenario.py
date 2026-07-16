import time
import os
from typing import Dict, Any
from infra.database import create_conn
from infra.ingestion import create_abbreviation
from core.pipeline import ScenarioConfig, ScenarioContext, ScenarioPipeline
from core.tasks import (
    IngestionTask, TopologyTask, GridTask, 
    RefactorTask, RoutingTask, ResultsTask, MappingTask
)
from core.telemetry import telemetry_manager

class ScenarioEngine:
    """
    ScenarioEngine: Deep orchestrator that utilizes the Pipeline/Task pattern.
    Provides leverage by decoupling stage execution from orchestration.
    """
    def __init__(self, db_config: Dict, sql_base_path: str, data_base_path: str):
        self.db_config = db_config
        self.sql_base_path = sql_base_path
        self.data_base_path = data_base_path
        self.conn = None

    def _get_conn(self):
        if not self.conn:
            self.conn = create_conn(
                self.db_config['name'], self.db_config['host'], 
                self.db_config['port'], self.db_config['user'], 
                self.db_config['password']
            )
        return self.conn

    def run(self, config: ScenarioConfig, observer: Any):
        start_time = time.time()
        conn = self._get_conn()
        
        location_prefix = create_abbreviation(config.location)
        scenario_prefix = f"{location_prefix}_{config.scenario_id}"
        
        # 1. Initialize Context & State (Locality)
        context = ScenarioContext(
            config=config,
            conn=conn,
            observer=observer,
            db_config=self.db_config,
            tables={
                'net': f"{scenario_prefix}_internal_net",
                'h3': f"{scenario_prefix}_internal_h3",
                'osm': f"{scenario_prefix}_osm_raw",
                'ciclo': f"{scenario_prefix}_ciclos",
                'projects': f"{scenario_prefix}_projects",
                'census': f"{scenario_prefix}_census",
                'zones': f"{scenario_prefix}_zones"
            },
            state={
                'sql_base_path': self.sql_base_path,
                'data_base_path': self.data_base_path
            }
        )

        # 2. Define Pipeline (Declarative Leverage)
        pipeline = ScenarioPipeline(context)
        pipeline.add_task(IngestionTask())
        pipeline.add_task(TopologyTask())
        pipeline.add_task(GridTask())
        pipeline.add_task(RefactorTask())
        pipeline.add_task(RoutingTask())
        pipeline.add_task(ResultsTask())
        pipeline.add_task(MappingTask())

        try:
            pipeline.execute()
            
            # Final Telemetry (Collect per-stage timings from observer)
            has_p = True if config.projects_input else False
            timings = observer.get_timings()
            timings['t_total'] = time.time() - start_time
            
            telemetry_manager.log_run(config.osm_input, config.od_input, has_p, config.srid, timings)
            
            # Close the loop: Train model with the new data point
            telemetry_manager.train_model()
            
            conn.commit()

        except Exception as e:
            conn.rollback()
            observer.report_diagnostic("ENGINE_CRASH", "ERROR", f"ScenarioEngine Pipeline Crash: {str(e)}")
            raise e
        finally:
            if config.cleanup:
                self._cleanup(context.tables)

    def _cleanup(self, tables):
        conn = self._get_conn()
        with conn.cursor() as cursor:
            for t in tables.values():
                cursor.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
            conn.commit()
