import os
from typing import Dict, Any, Optional
from core.pipeline import ScenarioConfig, ProgressSeam
from infra.database import execute_query, read_sql_file
from infra.ingestion import handle_path_argument, create_abbreviation
from ui.components import diagnostic_handler

class RoutingOrchestrator:
    """
    RoutingOrchestrator: A deep module implementing the Demand Routing seam.
    It encapsulates H3-to-node snapping, OD matrix loading, node-level demand consolidation,
    memory optimization settings, and batch pgRouting A* query executions.
    """
    def __init__(self, conn: Any, db_config: Dict[str, Any], sql_base_path: str, observer: Optional[ProgressSeam] = None):
        self.conn = conn
        self.db_config = db_config
        self.sql_base_path = sql_base_path
        self.observer = observer

    def _get_snapping_stats(self, scenario_prefix: str) -> tuple[int, int]:
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(f"SELECT count(*) FROM {scenario_prefix}_h3_to_node WHERE is_coverage_loss = false")
                snapped = cursor.fetchone()[0]
                cursor.execute(f"SELECT count(*) FROM {scenario_prefix}_h3_to_node")
                total = cursor.fetchone()[0]
                return snapped, total
        except Exception:
            return 0, 0

    def route(self, config: ScenarioConfig, tables: Dict[str, str]) -> str:
        """
        Executes the spatial matching and batch pgRouting assignation.
        Returns the components table name.
        """
        if self.observer:
            self.observer.on_progress_update("H3-to-Node Snapping", increment=1)

        location_prefix = create_abbreviation(config.location)
        scenario_prefix = f"{location_prefix}_{config.scenario_id}"
        internal_network_table = tables['net']
        h3_table_name = tables['h3']
        full_components_table = f"{internal_network_table}_components"

        if config.od_input:
            # 1. Re-calculate components to ensure we only snap to the LCC
            execute_query(self.conn, read_sql_file(os.path.join(self.sql_base_path, 'calculate_components.sql')).format(
                topo_name=f'{internal_network_table}_vertices_pgr', 
                result_table=full_components_table, 
                table_name=internal_network_table
            ))
            
            # 2. H3-to-Node Snapping
            execute_query(self.conn, read_sql_file(os.path.join(self.sql_base_path, 'snap_h3_to_network.sql')).format(
                location_prefix=scenario_prefix, 
                network_table=internal_network_table, 
                h3_table=h3_table_name, 
                components_table=full_components_table
            ))
            
            snapped, total = self._get_snapping_stats(scenario_prefix)
            diagnostic_handler.report(
                "SNAPPING_METRICS", 
                "INFO" if snapped > 0 else "ERROR", 
                f"Graph Snapping: {snapped}/{total} cells connected ({(snapped/total)*100 if total > 0 else 0:.1f}%)"
            )
            
            if snapped == 0:
                diagnostic_handler.report("H3_MISMATCH", "ERROR", "CRITICAL: No H3 cells from demand matrix matched the current grid. Check H3 Resolutions.")

        if config.od_input:
            if self.observer:
                self.observer.on_progress_update("Routing Demand", increment=1)
            
            # 3. Load demand dataset
            user = self.db_config.get('user')
            password = self.db_config.get('password')
            host = self.db_config.get('host')
            port = self.db_config.get('port')
            db = self.db_config.get('name')
            
            od_table_name = f"{scenario_prefix}_od_matrix"
            handle_path_argument(
                'od', config.od_input, None, od_table_name, config.location, 'None', config.srid,
                user, password, host, port, db, conn=self.conn
            )
            
            # 4. Node Consolidation (Prevents redundant routing cycles)
            diagnostic_handler.report("DEMAND_CONSOLIDATION", "INFO", "Consolidating H3 demand into unique graph nodes...")
            consolidated_table = f"{scenario_prefix}_node_demand_consolidated"
            execute_query(self.conn, f"DROP TABLE IF EXISTS {consolidated_table} CASCADE;")
            execute_query(self.conn, f"""
                CREATE TABLE {consolidated_table} AS
                SELECT 
                    o.node_id as source_node,
                    d.node_id as target_node,
                    SUM(m.trips) as total_trips
                FROM {od_table_name} m
                JOIN {scenario_prefix}_h3_to_node o ON m.h3_origin::text = o.h3_index::text
                JOIN {scenario_prefix}_h3_to_node d ON m.h3_dest::text = d.h3_index::text
                WHERE o.is_coverage_loss = false AND d.is_coverage_loss = false
                GROUP BY o.node_id, d.node_id;
            """)

            # 5. Batch routing step setup
            execute_query(self.conn, "SET work_mem = '128MB';")
            execute_query(self.conn, read_sql_file(os.path.join(self.sql_base_path, 'betweenness_init.sql')).format(network_table=internal_network_table))

            with self.conn.cursor() as cursor:
                cursor.execute(f"SELECT DISTINCT source_node FROM {scenario_prefix}_node_demand_consolidated")
                all_origins = [row[0] for row in cursor.fetchall()]

            diagnostic_handler.report("BATCH_ROUTING", "INFO", f"Executing A* Routing for {len(all_origins)} origins in chunks of 500...")
            
            chunk_size = 500
            query_template = read_sql_file(os.path.join(self.sql_base_path, 'od_routing_step_astar.sql'))

            for i in range(0, len(all_origins), chunk_size):
                chunk = all_origins[i:i + chunk_size]
                for origin_id in chunk:
                    execute_query(self.conn, query_template.format(
                        network_table=internal_network_table,
                        location_prefix=scenario_prefix,
                        origin_id=origin_id,
                        edge_weight_column='cost',
                        directed='false'
                    ))
                self.conn.commit()
                if self.observer:
                    self.observer.on_progress_update("Routing Demand", increment=len(chunk), total=len(all_origins))
                if (i // chunk_size) % 5 == 0:
                    print(f"     * Routed {i + len(chunk)}/{len(all_origins)} origins...")

            execute_query(self.conn, read_sql_file(os.path.join(self.sql_base_path, 'demand_finalize.sql')).format(network_table=internal_network_table))

        return full_components_table
