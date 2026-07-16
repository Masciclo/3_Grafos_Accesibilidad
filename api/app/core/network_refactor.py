import os
from typing import Dict, Any, Optional
from core.pipeline import ScenarioConfig, ProgressSeam
from infra.database import execute_query, read_sql_file
from infra.schema import SchemaGuard
from infra.ingestion import create_abbreviation
from ui.components import diagnostic_handler

class SpatialRefactorAdapter:
    """
    SpatialRefactorAdapter: A deep module implementing the Topological Refactor seam.
    It encapsulates PostGIS spatial refactoring, SQL query templating,
    suturing of project lines, and final network merging.
    """
    def __init__(self, conn: Any, sql_base_path: str, observer: Optional[ProgressSeam] = None):
        self.conn = conn
        self.sql_base_path = sql_base_path
        self.observer = observer

    def refactor(self, config: ScenarioConfig, tables: Dict[str, str]) -> str:
        """
        Executes multi-edge/single-edge project refactoring, creates impeded layers,
        merges baseline and processed elements, and repairs graph topology.
        """
        if self.observer:
            self.observer.on_progress_update("Refactorización de la Topología", increment=1)
            
        location_prefix = create_abbreviation(config.location)
        scenery_name = f"{location_prefix}_{config.scenario_id}_osm_proc"
        mr_dist = getattr(config, 'mr_distance', 5.0) 
        zp_dist = getattr(config, 'zp_distance', 25.0)
        
        osm_table = tables['osm']
        projects_table = tables['projects']
        internal_net_table = tables['net']
        ciclo_table = tables['ciclo']

        # --- Stage 5.1: High-Fidelity Invariant Prep ---
        SchemaGuard.ensure_network_parity(self.conn, osm_table)

        # --- Stage 5.2: ASSIMILATIVE REFACTORING ---
        if config.projects_input:
            if self.observer:
                self.observer.report_diagnostic("REFACTOR", "INFO", f"Executing Adaptive Suturing (MR={mr_dist}m, ZP={zp_dist}m)...")
            
            # Retrieve spatial SRID from baseline table
            with self.conn.cursor() as cur:
                try:
                    cur.execute(f"SELECT Find_SRID('public', '{osm_table}', 'geometry')")
                    srid = cur.fetchone()[0] or 32719
                except Exception:
                    srid = 32719
                    
            diag_prefix = f"{location_prefix}_{config.scenario_id}"
            
            # Initialize spatial diagnostic layers
            execute_query(self.conn, f"DROP TABLE IF EXISTS {diag_prefix}_diag_assim_buffers; CREATE TABLE {diag_prefix}_diag_assim_buffers (project_id BIGINT, geometry GEOMETRY(Geometry, {srid}));")
            execute_query(self.conn, f"DROP TABLE IF EXISTS {diag_prefix}_diag_shattered_segments; CREATE TABLE {diag_prefix}_diag_shattered_segments (parent_baseline_id BIGINT, project_id TEXT, highway TEXT, geometry GEOMETRY(Geometry, {srid}), overlap_pct DOUBLE PRECISION);")
            execute_query(self.conn, f"DROP TABLE IF EXISTS {diag_prefix}_diag_nodal_snaps; CREATE TABLE {diag_prefix}_diag_nodal_snaps (project_id TEXT, geometry GEOMETRY(Geometry, {srid}));")
            execute_query(self.conn, f"DROP TABLE IF EXISTS {diag_prefix}_diag_isolated_nodes; CREATE TABLE {diag_prefix}_diag_isolated_nodes (project_id TEXT, geometry GEOMETRY(Geometry, {srid}));")
            execute_query(self.conn, f"DROP TABLE IF EXISTS {diag_prefix}_diag_plugging_links; CREATE TABLE {diag_prefix}_diag_plugging_links (project_id TEXT, geometry GEOMETRY(Geometry, {srid}));")
            
            # Track A/B: Only execute spatial snapping/welding for user-drawn projects
            assimilated_segments = "temp_assimilated_segments"
            if config.scenario_id.startswith("rec_"):
                if self.observer:
                    self.observer.report_diagnostic("REFACTOR", "INFO", "Recommendation project detected. Bypassing spatial suturing...")
                execute_query(self.conn, f"CREATE TEMP TABLE {assimilated_segments} (project_id TEXT, parent_baseline_id TEXT, geometry GEOMETRY);")
            else:
                # Identify project archetypes (Single-Edge vs Multi-Edge)
                with self.conn.cursor() as cur:
                    cur.execute(f"SELECT id, COUNT(*) FROM {projects_table} GROUP BY id")
                    stats = cur.fetchall()
                    single_edge_pids = [row[0] for row in stats if row[1] == 1]
                    multi_edge_pids = [row[0] for row in stats if row[1] > 1]

                # Track A: Standard Iterative Shatter (for Multi-Edge)
                if multi_edge_pids:
                    if self.observer:
                        self.observer.report_diagnostic("SHATTER", "INFO", f"Applying iterative shatter to {len(multi_edge_pids)} multi-edge projects...")
                    
                    multi_ids_str = ",".join(map(str, multi_edge_pids))
                    execute_query(self.conn, f"""
                        DROP TABLE IF EXISTS multi_edge_projects; 
                        CREATE TEMP TABLE multi_edge_projects AS 
                        SELECT (ST_Dump(ST_MakeValid(geometry))).geom as geometry, id as id 
                        FROM {projects_table} 
                        WHERE id IN ({multi_ids_str});
                        CREATE INDEX multi_edge_projects_gix ON multi_edge_projects USING GIST (geometry);
                    """)
                    
                    assim_buffers = "temp_assimilation_buffers"
                    execute_query(self.conn, read_sql_file(os.path.join(self.sql_base_path, 'create_assimilation_buffers.sql')).format(
                        result_table=assim_buffers,
                        projects_table="multi_edge_projects",
                        mr_distance=mr_dist
                    ))

                    execute_query(self.conn, read_sql_file(os.path.join(self.sql_base_path, 'resolve_assimilation_conflicts.sql')).format(
                        result_table=assimilated_segments,
                        baseline_table=osm_table,
                        buffers_table=assim_buffers
                    ))
                    
                    # Save multi-edge diagnostics
                    execute_query(self.conn, f"TRUNCATE {diag_prefix}_diag_assim_buffers; INSERT INTO {diag_prefix}_diag_assim_buffers SELECT * FROM {assim_buffers};")
                    execute_query(self.conn, f"TRUNCATE {diag_prefix}_diag_shattered_segments; INSERT INTO {diag_prefix}_diag_shattered_segments SELECT * FROM {assimilated_segments};")

                    # Apply Assimilation
                    execute_query(self.conn, f"DELETE FROM {osm_table} WHERE id IN (SELECT parent_baseline_id FROM {assimilated_segments});")
                    execute_query(self.conn, f"""
                        INSERT INTO {osm_table} (geometry, highway, is_project, project_id, parent_baseline_id, impedance) 
                        SELECT geometry, 'project_assimilated', TRUE, project_id::text, parent_baseline_id, 0.5 
                        FROM {assimilated_segments};
                    """)
                    
                    # Innovation path for multi-edge: geometries that do not significantly overlap baseline
                    execute_query(self.conn, f"""
                        INSERT INTO {osm_table} (geometry, highway, is_project, project_id, impedance) 
                        SELECT p.geometry, 'project_innovation', TRUE, p.id::text, 0.5 
                        FROM multi_edge_projects p 
                        WHERE NOT EXISTS (
                            SELECT 1 FROM {assimilated_segments} s 
                            WHERE s.project_id::bigint = p.id 
                              AND ST_Intersects(p.geometry, s.geometry)
                              AND ST_Length(ST_Intersection(p.geometry, s.geometry)) > 0.5 * ST_Length(p.geometry)
                        );
                    """)
                else:
                    execute_query(self.conn, f"CREATE TEMP TABLE {assimilated_segments} (project_id TEXT, parent_baseline_id TEXT, geometry GEOMETRY);")

                # Track B: Nodalized Sutura Pattern (for Single-Edge)
                if single_edge_pids:
                    if self.observer:
                        self.observer.report_diagnostic("SUTURA", "INFO", f"Applying Nodalized Sutura to {len(single_edge_pids)} single-edge projects...")
                    
                    single_ids_str = ",".join(map(str, single_edge_pids))
                    execute_query(self.conn, f"""
                        INSERT INTO {osm_table} (geometry, highway, is_project, project_id, impedance) 
                        SELECT (ST_Dump(ST_MakeValid(geometry))).geom, 'project_innovation', TRUE, id::text, 0.5 
                        FROM {projects_table} WHERE id IN ({single_ids_str});
                    """)
                    
                    # Sequential single-edge link sutures
                    for pid in single_edge_pids:
                        execute_query(self.conn, read_sql_file(os.path.join(self.sql_base_path, 'link_single_edge_project.sql')).format(
                            network_table=osm_table,
                            pid=pid,
                            mr_distance=mr_dist,
                            zp_distance=zp_dist,
                            diag_snaps_table=f"{diag_prefix}_diag_nodal_snaps"
                        ))

        # --- Stage 5.4: INHIBITION (Impedance Surface) ---
        if self.observer:
            self.observer.on_progress_update("Refactorización de la Topología", increment=1)
            
        # Create raw OSM street danger-zone impedance buffers
        execute_query(self.conn, read_sql_file(os.path.join(self.sql_base_path, 'create_impedance_buffers.sql')).format(
            result_table=f'{scenery_name}_imp_buff', 
            table_name=osm_table, 
            dist_buffer=config.buffer_size, 
            high_impedance=config.imp_primary, 
            medium_impedance=config.imp_secondary, 
            low_impedance=config.imp_tertiary, 
            else_impedance=config.imp_local
        ))

        # Check if disinhibition (bikelane buffer subtraction) is enabled
        use_buffer = f'{scenery_name}_imp_buff'
        if config.disinhibit:
            if self.observer:
                self.observer.report_diagnostic("DISINHIBITION", "INFO", "Executing cycleway desinhibition buffer subtraction...")
            
            des_lines = f'{scenery_name}_desinhibitor_lines'
            execute_query(self.conn, f"DROP TABLE IF EXISTS public.{des_lines};")
            execute_query(self.conn, read_sql_file(os.path.join(self.sql_base_path, 'union_desinhibit.sql')).format(
                desinhibitor_name=des_lines,
                ciclo_table=ciclo_table,
                desinhibitor_table=tables['projects'] if config.projects_input else ciclo_table,
                filters=""
            ))
            
            des_buff = f'{scenery_name}_desinhibitor_buff'
            execute_query(self.conn, f"DROP TABLE IF EXISTS buffers.{des_buff};")
            execute_query(self.conn, read_sql_file(os.path.join(self.sql_base_path, 'create_buffer.sql')).format(
                result_table=des_buff,
                table_name=f"public.{des_lines}",
                dist_buffer=config.buffer_size
            ))
            
            imp_diff = f'{scenery_name}_imp_diff'
            execute_query(self.conn, f"DROP TABLE IF EXISTS buffers.{imp_diff};")
            execute_query(self.conn, f"DROP TABLE IF EXISTS buffers.{scenery_name}_inhib_diff;")
            execute_query(self.conn, read_sql_file(os.path.join(self.sql_base_path, 'buffer_difference.sql')).format(
                inhib_name=f'{scenery_name}_inhib_diff',
                buffer_inhibitor=f'{scenery_name}_imp_buff',
                buffer_desinhibitor=des_buff,
                impedance_name=imp_diff,
                buffer_impedance=f'{scenery_name}_imp_buff'
            ))
            
            use_buffer = imp_diff

        # Run inhibition step using the appropriate buffer (subtracted or raw)
        execute_query(self.conn, read_sql_file(os.path.join(self.sql_base_path, 'create_inhibited_network.sql')).format(
            result_name=scenery_name, 
            network_table=osm_table, 
            inhib_buffer=use_buffer, 
            impedance_buffer=use_buffer
        ))

        # --- Stage 6: MERGING ---
        projects_union = ""
        if config.projects_input and config.scenario_id.startswith("rec_"):
            projects_union = f"""
            UNION ALL
            SELECT 
                (ST_Dump(ST_MakeValid(geometry))).geom as geometry,
                {config.imp_bike}::float as impedance,
                'cycleway'::text as highway,
                'cycleway'::text as original_highway,
                TRUE as is_project,
                project_id::text as project_id,
                parent_baseline_id::integer as parent_baseline_id
            FROM {projects_table}
            WHERE geometry IS NOT NULL
            """

        execute_query(self.conn, read_sql_file(os.path.join(self.sql_base_path, 'create_full_network.sql')).format(
            result_name=internal_net_table, 
            ciclo=ciclo_table, 
            osm=scenery_name, 
            filters="", 
            bike_impedance=config.imp_bike,
            projects_union=projects_union
        ))

        # --- Stage 6.5: FINAL TOPOLOGICAL REPAIR (Phase 19.5 Fix) ---
        if self.observer:
            self.observer.report_diagnostic("TOPOLOGY_FINAL", "INFO", "Building final routing topology...")
            
        execute_query(self.conn, read_sql_file(os.path.join(self.sql_base_path, 'create_routing_topology.sql')).format(
            table=internal_net_table, 
            tolerance=0.1
        ))

        # --- Stage 6.6: Snap Baseline Cycleways to Street Network (Welding) ---
        if self.observer:
            self.observer.report_diagnostic("CYCLEWAY_WELD", "INFO", "Welding isolated baseline cycleway endpoints to street network...")
        execute_query(self.conn, f"""
            DROP TABLE IF EXISTS temp_cycleway_node_degrees;
            CREATE TEMP TABLE temp_cycleway_node_degrees AS
            SELECT node_id, COUNT(*) as degree
            FROM (
                SELECT source as node_id FROM {internal_net_table} WHERE original_highway = 'cycleway'
                UNION ALL
                SELECT target as node_id FROM {internal_net_table} WHERE original_highway = 'cycleway'
            ) sub
            GROUP BY node_id;

            DROP TABLE IF EXISTS temp_isolated_cycleway_nodes;
            CREATE TEMP TABLE temp_isolated_cycleway_nodes AS
            SELECT 
                d.node_id,
                v.the_geom
            FROM temp_cycleway_node_degrees d
            JOIN {internal_net_table}_vertices_pgr v ON d.node_id = v.id
            WHERE d.degree = 1 -- Only snap dead-ends of cycleways!
              AND NOT EXISTS (
                  SELECT 1 FROM {internal_net_table} e 
                  WHERE (e.source = d.node_id OR e.target = d.node_id) 
                    AND e.original_highway != 'cycleway'
              );


            DROP TABLE IF EXISTS temp_cycleway_plugging_map;
            CREATE TEMP TABLE temp_cycleway_plugging_map AS
            SELECT DISTINCT ON (i.node_id)
                i.node_id as isolated_node_id,
                target.id as target_node_id
            FROM temp_isolated_cycleway_nodes i
            CROSS JOIN LATERAL (
                SELECT v.id 
                FROM {internal_net_table}_vertices_pgr v
                WHERE v.id NOT IN (SELECT node_id FROM temp_isolated_cycleway_nodes)
                  AND ST_DWithin(i.the_geom, v.the_geom, 30.0)
                  AND EXISTS (SELECT 1 FROM {internal_net_table} e WHERE (e.source = v.id OR e.target = v.id) AND e.original_highway != 'cycleway')
                ORDER BY i.the_geom <-> v.the_geom
                LIMIT 1
            ) target;

            UPDATE {internal_net_table} SET source = m.target_node_id 
            FROM temp_cycleway_plugging_map m 
            WHERE source = m.isolated_node_id AND original_highway = 'cycleway';

            UPDATE {internal_net_table} SET target = m.target_node_id 
            FROM temp_cycleway_plugging_map m 
            WHERE target = m.isolated_node_id AND original_highway = 'cycleway';
        """)


        if config.projects_input and not config.scenario_id.startswith("rec_"):
            if self.observer:
                self.observer.report_diagnostic("NODALIZATION", "INFO", "Executing Project-specific Nodalization & Repair...")
            
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT DISTINCT project_id FROM {internal_net_table} WHERE is_project = TRUE")
                project_ids = [row[0] for row in cur.fetchall()]

            for pid in project_ids:
                if not pid: continue
                if self.observer:
                    self.observer.report_diagnostic("PROJECT_PLUG", "INFO", f"Plugging project endpoints: {pid}")
                execute_query(self.conn, read_sql_file(os.path.join(self.sql_base_path, 'plug_project_nodes.sql')).format(
                    network_table=internal_net_table,
                    mr_distance=mr_dist,
                    pid=pid,
                    diag_nodes_table=f"{diag_prefix}_diag_isolated_nodes",
                    diag_links_table=f"{diag_prefix}_diag_plugging_links"
                ))

        # Final Graph Cleaning
        execute_query(self.conn, f"DELETE FROM {internal_net_table} WHERE ST_Length(geometry) < 0.5;")

        return scenery_name
