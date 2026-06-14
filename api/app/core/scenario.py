from dataclasses import dataclass, field
from typing import List, Optional, Dict
from abc import ABC, abstractmethod

@dataclass
class ScenarioConfig:
    """
    ScenarioConfig: The unified data structure for a simulation run.
    """
    location: str
    city_key: str  # Task 13.13: Explicit disk folder name
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
    mr_distance: float = 5.0  # Magnetismo a Referencia (Assimilation)
    ma_distance: float = 7.0  # Magnetismo a Antecesor (Lineage)
    zp_distance: float = 25.0 # Zona de Proyecto (Audit Clip)
    
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

import time
import os
from infra.database import create_conn, execute_query, read_sql_file, check_table_existence
from infra.ingestion import handle_path_argument, download_h3, extract_h3_grid_from_od, create_abbreviation
from core import topology_refactor, routing, results
from core.telemetry import telemetry_manager

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
    def report_diagnostic(self, level: str, message: str):
        pass

class ScenarioEngine:
    """
    ScenarioEngine: The deep module for pipeline orchestration.
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

    def run(self, config: ScenarioConfig, observer: ProgressSeam):
        start_time = time.time()
        timings = {}
        conn = self._get_conn()
        
        location_prefix = create_abbreviation(config.location)
        scenario_prefix = f"{location_prefix}_{config.scenario_id}"
        
        # Internal table names derived from scenario_prefix
        tables = {
            'net': f"{scenario_prefix}_internal_net",
            'h3': f"{scenario_prefix}_internal_h3",
            'osm': f"{scenario_prefix}_osm_raw",
            'ciclo': f"{scenario_prefix}_ciclos",
            'projects': f"{scenario_prefix}_projects",
            'census': f"{scenario_prefix}_census",
            'zones': f"{scenario_prefix}_zones"
        }

        try:
            has_p = True if config.projects_input else False

            # --- Stage 1: Ingestion ---
            observer.on_stage_start(1, "Data Ingestion", eta=telemetry_manager.format_eta(telemetry_manager.predict_eta(config.osm_input, config.od_input, has_p, stage='ingestion')))
            s1_start = time.time()
            
            # 1.1. OSM & Bike
            handle_path_argument('osm', config.osm_input, os.path.join(self.data_base_path, 'highways.geojson'), tables['osm'], config.location, 'LineString', config.srid, self.db_config['user'], self.db_config['password'], self.db_config['host'], self.db_config['port'], self.db_config['name'], bbox=config.bbox)
            bike_source = config.ciclo_input or (config.osm_input if (config.osm_input and os.path.exists(config.osm_input)) else 'osm')
            handle_path_argument('bike', bike_source, os.path.join(self.data_base_path, 'ciclo.geojson'), tables['ciclo'], config.location, 'LineString', config.srid, self.db_config['user'], self.db_config['password'], self.db_config['host'], self.db_config['port'], self.db_config['name'], bbox=config.bbox)
            
            # 1.2. Zones
            zones_path = os.path.join(self.data_base_path, config.city_key, 'raw', f"{config.city_key}_zones", 'zones.shp')
            handle_path_argument('zones', zones_path, None, tables['zones'], config.location, 'MultiPolygon', config.srid, self.db_config['user'], self.db_config['password'], self.db_config['host'], self.db_config['port'], self.db_config['name'])

            # 1.3. Census & Projects
            if config.projects_input:
                handle_path_argument('projects', config.projects_input, None, tables['projects'], config.location, 'LineString', config.srid, self.db_config['user'], self.db_config['password'], self.db_config['host'], self.db_config['port'], self.db_config['name'])
            handle_path_argument('census', config.census_input, None, tables['census'], config.location, 'MultiPolygon', config.srid, self.db_config['user'], self.db_config['password'], self.db_config['host'], self.db_config['port'], self.db_config['name'], bbox=config.bbox)
            
            timings['t_ingestion'] = time.time() - s1_start
            observer.on_stage_end(1)

            # --- Stage 2: Topology ---
            observer.on_stage_start(2, "Topology Creation", eta=telemetry_manager.format_eta(telemetry_manager.predict_eta(config.osm_input, config.od_input, has_p, stage='topo')))
            s2_start = time.time()
            execute_query(conn, read_sql_file(os.path.join(self.sql_base_path, 'create_routing_topology.sql')).format(table=tables['osm'], tolerance=0.1))
            execute_query(conn, read_sql_file(os.path.join(self.sql_base_path, 'calculate_components.sql')).format(topo_name=f"{tables['osm']}_vertices_pgr", result_table=f"{tables['osm']}_components", table_name=tables['osm']))
            timings['t_topo'] = time.time() - s2_start
            observer.on_stage_end(2)

            # --- Stage 3: Grid Extraction ---
            observer.on_stage_start(3, "Grid Extraction", eta=telemetry_manager.format_eta(telemetry_manager.predict_eta(config.osm_input, config.od_input, has_p, stage='grid')))
            s3_start = time.time()
            download_h3(
                tables['zones'], tables['h3'], config.srid, int(os.getenv('H3_LEVEL', 9)), 
                self.db_config['user'], self.db_config['password'], self.db_config['host'], 
                self.db_config['port'], self.db_config['name'],
                callback=lambda *args, **kwargs: observer.on_progress_update(*args, **kwargs)
            )
            observer.on_progress_update("ADVANCE_GRID", increment=100)
            execute_query(conn, read_sql_file(os.path.join(self.sql_base_path, 'prune_h3_to_mcp.sql')).format(zones_table=tables['zones'], h3_table=tables['h3']))
            timings['t_grid'] = time.time() - s3_start
            observer.on_stage_end(3)

            # --- Stage 5: Refactorización de la Topología ---
            observer.on_stage_start(5, "Refactorización de la Topología", eta=telemetry_manager.format_eta(telemetry_manager.predict_eta(config.osm_input, config.od_input, has_p, stage='refactor')))
            s5_start = time.time()
            topology_refactor.run_topological_refactor(
                conn, config, tables['osm'], tables['projects'], location_prefix, 
                tables['net'], tables['ciclo'], self.sql_base_path, 
                callback=lambda *args, **kwargs: observer.on_progress_update(*args, **kwargs)
            )
            timings['t_refactor'] = time.time() - s5_start
            observer.on_stage_end(5)

            # --- Stage 7: Demand Routing ---
            observer.on_stage_start(7, "Demand Routing", eta=telemetry_manager.format_eta(telemetry_manager.predict_eta(config.osm_input, config.od_input, has_p, stage='routing')))
            s7_start = time.time()
            routing.run_demand_routing(
                conn, config, tables['net'], location_prefix, tables['h3'], 
                self.sql_base_path, self.db_config['user'], self.db_config['password'], 
                self.db_config['host'], self.db_config['port'], self.db_config['name'],
                callback=lambda *args, **kwargs: observer.on_progress_update(*args, **kwargs)
            )
            timings['t_routing'] = time.time() - s7_start
            observer.on_stage_end(7)

            # --- Stage 8: H3 Aggregation ---
            observer.on_stage_start(8, "H3 Aggregation", eta=telemetry_manager.format_eta(telemetry_manager.predict_eta(config.osm_input, config.od_input, has_p, stage='agg')))
            s8_start = time.time()
            results.run_aggregation_and_delta(
                conn, config, location_prefix, scenario_prefix, tables['net'], tables['h3'], 
                tables['osm'], tables['ciclo'], tables['projects'], tables['census'], 
                config.od_input, config.census_input, self.sql_base_path, config.srid,
                ma_distance=config.ma_distance,
                callback=lambda *args, **kwargs: observer.on_progress_update(*args, **kwargs)
            )
            timings['t_agg'] = time.time() - s8_start
            observer.on_stage_end(8)

            # --- Stage 9: Cierre Analítico y Auditoría ---
            observer.on_stage_start(9, "Cierre Analítico y Auditoría", eta=telemetry_manager.format_eta(telemetry_manager.predict_eta(config.osm_input, config.od_input, has_p, stage='final')))
            s9_start = time.time()
            results.finalize_qgis_layers(
                conn, scenario_prefix, tables['net'], tables['h3'], tables['ciclo'], 
                self.sql_base_path, config, callback=None,
                census_table_name=tables['census'], osm_table_name=tables['osm'],
                zones_table_name=tables['zones'], city_key=config.city_key
            )
            timings['t_final'] = time.time() - s9_start
            observer.on_stage_end(9)

            # Final Telemetry
            timings['t_total'] = time.time() - start_time
            telemetry_manager.log_run(config.osm_input, config.od_input, has_p, config.srid, timings)
            conn.commit()

        except Exception as e:
            conn.rollback()
            observer.report_diagnostic("ERROR", f"ScenarioEngine Crash: {str(e)}")
            raise e
        finally:
            if config.cleanup:
                self._cleanup(tables)

    def _cleanup(self, tables):
        conn = self._get_conn()
        with conn.cursor() as cursor:
            for t in tables.values():
                cursor.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
            conn.commit()
