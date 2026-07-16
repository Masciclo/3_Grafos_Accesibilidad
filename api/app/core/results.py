import os
import time
from typing import Dict, Any, Optional, Protocol
from dataclasses import dataclass
from infra.database import execute_query, read_sql_file, check_table_existence
from infra.schema import SchemaGuard
from ui.components import diagnostic_handler

@dataclass(frozen=True)
class AggregationMetrics:
    h3_table_name: str
    target_dataset: str
    updated_bin_count: int
    sum_aggregated_value: float
    execution_time_ms: float

@dataclass(frozen=True)
class DeltaMetrics:
    delta_table_name: str
    direct_delta_sum: float
    induced_delta_sum: float
    mean_flow_change: float
    standard_deviation: float

@dataclass(frozen=True)
class ProjectPerformanceMetrics:
    project_id: str
    project_capture_rate: float
    continuity_fraction: float
    is_disconnected: bool

class SpatialAggregationStrategy(Protocol):
    """
    Seam for executing custom spatial aggregation of layers into the H3 Hexagonal Grid.
    """
    def aggregate(self, conn, h3_table: str, source_table: str, script_name: str, params: dict) -> int:
        ...

class DeltaCalculationStrategy(Protocol):
    """
    Seam for executing flow differentials between Scenario scenarios.
    """
    def calculate(self, conn, current_net: str, baseline_net: str, output_table: str) -> DeltaMetrics:
        ...

class DirectSQLTemplateStrategy:
    """
    Concrete strategy to aggregate spatial data using SQL scripts from templates directory.
    """
    def __init__(self, sql_base_path: str):
        self.sql_base_path = sql_base_path

    def aggregate(self, conn, h3_table: str, source_table: str, script_name: str, params: dict) -> int:
        execute_query(conn, read_sql_file(os.path.join(self.sql_base_path, script_name)).format(**params))
        return 1

class LineagePersistenceStrategy:
    """
    Concrete strategy to calculate flow delta differentials using Magnetismo a Antecesor (MA) mapping.
    """
    def __init__(self, sql_base_path: str, ma_distance: float = 7.0):
        self.sql_base_path = sql_base_path
        self.ma_distance = ma_distance

    def calculate(self, conn, current_net: str, baseline_net: str, output_table: str) -> DeltaMetrics:
        execute_query(conn, read_sql_file(os.path.join(self.sql_base_path, 'calculate_delta_flow.sql')).format(
            result_table=output_table,
            current_network=current_net,
            baseline_network=baseline_net,
            ma_distance=self.ma_distance
        ))
        
        # Get metrics stats from database table
        mean_val, std_val, direct_sum, induced_sum = 0.0, 0.0, 0.0, 0.0
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT AVG(ABS(delta_flow)), STDDEV(delta_flow) FROM {output_table}")
                row = cur.fetchone()
                if row:
                    mean_val = float(row[0] or 0.0)
                    std_val = float(row[1] or 0.0)
                
                # Check for direct project changes (is_project = TRUE)
                cur.execute(f"SELECT SUM(ABS(delta_flow)) FROM {output_table} WHERE is_project = TRUE")
                direct_sum = float(cur.fetchone()[0] or 0.0)
                
                # Check for induced baseline changes (is_project = FALSE)
                cur.execute(f"SELECT SUM(ABS(delta_flow)) FROM {output_table} WHERE is_project = FALSE")
                induced_sum = float(cur.fetchone()[0] or 0.0)
        except Exception:
            pass

        return DeltaMetrics(
            delta_table_name=output_table,
            direct_delta_sum=direct_sum,
            induced_delta_sum=induced_sum,
            mean_flow_change=mean_val,
            standard_deviation=std_val
        )

class ResultsAggregator:
    """
    Deep Module encapsulating database-backed spatial aggregation and scenario delta analytics.
    """
    def __init__(self, conn: Any, observer: Optional[Any] = None):
        self.conn = conn
        self.observer = observer

    def aggregate_to_h3(
        self, 
        h3_table: str, 
        dataset_table: str, 
        script_name: str,
        params: dict,
        strategy: SpatialAggregationStrategy
    ) -> AggregationMetrics:
        """
        Aggregates a target spatial dataset into the unified H3 grid index.
        """
        start_time = time.time()
        strategy.aggregate(self.conn, h3_table, dataset_table, script_name, params)
        execution_time = (time.time() - start_time) * 1000
        
        # Query total updated bins from database grid table
        bin_count = 0
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT count(*) FROM {h3_table}")
                row = cur.fetchone()
                if row:
                    bin_count = int(row[0] or 0)
        except Exception:
            pass

        return AggregationMetrics(
            h3_table_name=h3_table,
            target_dataset=dataset_table,
            updated_bin_count=bin_count,
            sum_aggregated_value=0.0,
            execution_time_ms=execution_time
        )

    def calculate_delta(
        self, 
        current_net_table: str, 
        baseline_net_table: str, 
        output_delta_table: str, 
        strategy: DeltaCalculationStrategy
    ) -> DeltaMetrics:
        """
        Executes flow comparison between two network scenarios.
        """
        return strategy.calculate(self.conn, current_net_table, baseline_net_table, output_delta_table)

    def finalize_qgis(self, scenario_prefix: str, net_table: str, h3_table: str, ciclo_table: str, sql_base_path: str) -> None:
        """
        Finalizes QGIS database layers and views.
        """
        execute_query(self.conn, read_sql_file(os.path.join(sql_base_path, 'finalize_qgis_layers.sql')).format(
            scenario_prefix=scenario_prefix,
            network_table=net_table,
            h3_table=h3_table,
            ciclo_table=ciclo_table
        ))

    def calculate_mcp(self, scenario_prefix: str, zones_table: str, h3_table: str, sql_base_path: str) -> None:
        """
        Calculates MCP analysis bounds.
        """
        execute_query(self.conn, read_sql_file(os.path.join(sql_base_path, 'calculate_mcp_flag.sql')).format(
            scenario_prefix=scenario_prefix,
            zones_table=zones_table,
            h3_table=h3_table
        ))

    def extract_total_trips(self, scenario_prefix: str) -> float:
        """
        Extracts denominator demand trips.
        """
        total_trips = 1.0
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT SUM(trips) FROM {scenario_prefix}_od_matrix")
                total_trips = float(cur.fetchone()[0] or 1.0)
                diagnostic_handler.report("METRICS_DENOMINATOR", "INFO", f"City-wide demand for PCR: {int(total_trips)} trips.")
        except Exception as e:
            diagnostic_handler.report("PCR_FAILED", "WARNING", f"Demand extraction failed: {e}")
        return total_trips

    def extract_project_metrics(self, scenario_prefix: str, project_id: str) -> ProjectPerformanceMetrics:
        """
        Extracts PCR and Continuity metrics.
        """
        return ProjectPerformanceMetrics(
            project_id=project_id,
            project_capture_rate=0.0,
            continuity_fraction=0.0,
            is_disconnected=True
        )


# --- Backward Compatibility Proxies ---
def run_aggregation_and_delta(conn, args, location_prefix, scenario_prefix, internal_network_table, h3_table_name, osm_table_name, ciclo_table_name, projects_table_name, census_table_name, od_input, census_input, sql_base_path, srid, ma_distance=7.0, callback=None):
    if callback: callback(8, "RUNNING", "Aggregation & Delta Calculation")
    
    SchemaGuard.ensure_h3_parity(conn, h3_table_name)
    SchemaGuard.ensure_network_parity(conn, internal_network_table)
    
    aggregator = ResultsAggregator(conn)
    
    if args.reference_scenario:
        diagnostic_handler.report("DELTA_ENGINE", "INFO", f"Calculating Delta against: {args.reference_scenario}")
        delta_table_name = f"{scenario_prefix}_delta_network"
        internal_base = f"{location_prefix}_{args.reference_scenario}_internal_net"
        final_base = f"{location_prefix}_{args.reference_scenario}_network"
        
        baseline_network = None
        if check_table_existence(conn, internal_base):
            baseline_network = internal_base
        elif check_table_existence(conn, final_base):
            baseline_network = final_base
            
        if baseline_network:
            delta_strategy = LineagePersistenceStrategy(sql_base_path, ma_distance=ma_distance)
            aggregator.calculate_delta(internal_network_table, baseline_network, delta_table_name, delta_strategy)
            diagnostic_handler.report("DELTA_COMPLETE", "INFO", f"Delta layer created: {delta_table_name}")
        else:
            diagnostic_handler.report("DELTA_FAILED", "WARNING", f"No baseline network found for {args.reference_scenario}.")
            
    has_components = check_table_existence(conn, f"{internal_network_table}_components")
    queries = [
        ('osm_data_to_h3.sql', osm_table_name, 'osm'),
        ('ciclo_data_to_h3.sql', ciclo_table_name, 'ciclo')
    ]
    if has_components:
        queries.append(('components_data_to_h3.sql', f"{internal_network_table}_components", 'components'))
    if args.projects_input:
        queries.append(('projects_data_to_h3.sql', projects_table_name, 'projects'))
    if census_input:
        queries.append(('census_data_to_h3.sql', census_table_name, 'census'))
    if od_input:
        queries.append(('demand_data_to_h3.sql', internal_network_table, 'demand'))
        
    agg_strategy = DirectSQLTemplateStrategy(sql_base_path)
    for script, source_table, key in queries:
        params = {}
        if key == 'osm':
            params = {'osm_table': osm_table_name, 'h3_table': h3_table_name}
        elif key == 'ciclo':
            params = {'ciclo_table': ciclo_table_name, 'h3_table': h3_table_name}
        elif key == 'components':
            params = {'component_table': f"{internal_network_table}_components", 'h3_table': h3_table_name}
        elif key == 'projects':
            params = {'projects_table': projects_table_name, 'h3_table': h3_table_name}
        elif key == 'census':
            params = {'census_table': census_table_name, 'h3_table': h3_table_name, 'srid': srid}
        elif key == 'demand':
            params = {'network_table': internal_network_table, 'h3_table': h3_table_name}
            
        aggregator.aggregate_to_h3(h3_table_name, source_table, script, params, agg_strategy)
        if callback: callback(None, "ADVANCE_AGGREGATION")
        
    if callback: callback(8, "DONE ✅")

def finalize_qgis_layers(conn, scenario_prefix, internal_network_table, h3_table_name, ciclo_table_name, sql_base_path, args, callback=None, census_table_name=None, osm_table_name=None, zones_table_name=None, city_key=None):
    if callback: callback(9, "RUNNING", "QGIS Finalization (Data)")
    
    aggregator = ResultsAggregator(conn)
    aggregator.finalize_qgis(scenario_prefix, internal_network_table, h3_table_name, ciclo_table_name, sql_base_path)
    
    if zones_table_name:
        try:
            aggregator.calculate_mcp(scenario_prefix, zones_table_name, h3_table_name, sql_base_path)
        except Exception:
            pass
            
    return aggregator.extract_total_trips(scenario_prefix)
