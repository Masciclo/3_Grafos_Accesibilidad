import os
from infra.database import execute_query, read_sql_file
from infra.schema import SchemaGuard
from ui.components import diagnostic_handler

def run_topological_refactor(conn, args, osm_table_name, projects_table_name, location_prefix, internal_network_table, ciclo_table_name, sql_base_path, callback=None):
    """
    Task 18.4 (Iterative): Orchestrates the Refactoring by Assimilation sequence per Project ID.
    STRATEGY: Per-Project Autonomy with Pre-flight Greatest Overlap Resolver.
    """
    if callback: callback(5, "RUNNING", "Refactorización de la Topología")
    scenery_name = f'{location_prefix}_{args.scenario_id}_osm_proc'
    mr_dist = getattr(args, 'mr_distance', 5.0) 
    zp_dist = getattr(args, 'zp_distance', 25.0) 

    # --- Stage 5.1: High-Fidelity Invariant Prep ---
    execute_query(conn, f"ALTER TABLE {osm_table_name} ADD COLUMN IF NOT EXISTS is_project BOOLEAN DEFAULT FALSE;")
    execute_query(conn, f"ALTER TABLE {osm_table_name} ADD COLUMN IF NOT EXISTS project_id TEXT;")
    execute_query(conn, f"ALTER TABLE {osm_table_name} ADD COLUMN IF NOT EXISTS parent_baseline_id INTEGER;") 
    execute_query(conn, f"ALTER TABLE {osm_table_name} ADD COLUMN IF NOT EXISTS impedance DOUBLE PRECISION DEFAULT 1.0;")

    # --- Stage 5.2: ASSIMILATIVE REFACTORING ---
    if args.projects_input:
        diagnostic_handler.report("REFACTOR", "INFO", f"Executing Iterative Assimilation (MR={mr_dist}m, ZP={zp_dist}m)...")
        
        # 1. Global Pre-flight: Identify Conquest Map (Greatest Overlap)
        # This prevents projects from fighting over the same segment DURING iteration.
        assim_buffers = "temp_assimilation_buffers"
        execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'create_assimilation_buffers.sql')).format(
            result_table=assim_buffers,
            projects_table=projects_table_name,
            mr_distance=mr_dist
        ))

        assimilated_segments = "temp_assimilated_segments"
        execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'resolve_assimilation_conflicts.sql')).format(
            result_table=assimilated_segments,
            baseline_table=osm_table_name,
            buffers_table=assim_buffers
        ))

        # 2. Get list of unique projects to process iteratively
        with conn.cursor() as cur:
            cur.execute(f"SELECT DISTINCT project_id FROM {assimilated_segments} WHERE project_id IS NOT NULL")
            project_ids = [row[0] for row in cur.fetchall()]
            
            # Also add projects that are PURE innovation (no assimilation)
            cur.execute(f"SELECT DISTINCT id FROM {projects_table_name} WHERE id NOT IN (SELECT project_id FROM {assimilated_segments})")
            innovation_ids = [row[0] for row in cur.fetchall()]
            
            all_project_ids = sorted(list(set(project_ids + innovation_ids)))

        diagnostic_handler.report("ITERATIVE_REFACTOR", "INFO", f"Processing {len(all_project_ids)} independent projects...")

        for pid in all_project_ids:
            diagnostic_handler.report("PROJECT_PROCESS", "INFO", f"Refactoring Project ID: {pid}")
            
            # 2.1 Apply Assimilation for this specific PID
            # Remove original baseline segments assigned to this PID
            execute_query(conn, f"""
                DELETE FROM {osm_table_name} 
                WHERE id IN (SELECT parent_baseline_id FROM {assimilated_segments} WHERE project_id = '{pid}');
            """)

            # Inject assimilated segments for this PID
            execute_query(conn, f"""
                INSERT INTO {osm_table_name} (geometry, highway, is_project, project_id, parent_baseline_id, impedance)
                SELECT 
                    geometry, 'project_assimilated', TRUE, project_id, parent_baseline_id, 0.5
                FROM {assimilated_segments}
                WHERE project_id = '{pid}';
            """)

            # 2.2 Inject Innovation for this specific PID (if applicable)
            execute_query(conn, f"""
                INSERT INTO {osm_table_name} (geometry, highway, is_project, project_id, impedance)
                SELECT 
                    p.geometry, 'project_innovation', TRUE, p.id, 0.5
                FROM {projects_table_name} p
                WHERE p.id = '{pid}' AND NOT EXISTS (
                    SELECT 1 FROM {assimilated_segments} s WHERE s.project_id = p.id
                );
            """)

            # 2.3 Isolated Suture for this specific PID
            # We pass pid to SQL to ensure Isolation of Snapping
            execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'snap_and_shatter_projects.sql')).format(
                network_table=osm_table_name,
                mr_distance=mr_dist,
                zp_distance=zp_dist,
                pid=pid
            ))

        # 3. Final Noise Filter implementation (Global pass after all iterations)
        execute_query(conn, f"DELETE FROM {osm_table_name} WHERE ST_Length(geometry) < 0.5;")

    # --- Stage 5.4: INHIBITION (Impedance Surface) ---
    if callback: callback(None, "ADVANCE_REFACTOR") 
    execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'create_impedance_buffers.sql')).format(
        result_table=f'{scenery_name}_imp_buff', 
        table_name=osm_table_name, 
        dist_buffer=args.buffer_size,
        high_impedance=args.imp_primary, 
        medium_impedance=args.imp_secondary, 
        low_impedance=args.imp_tertiary, 
        else_impedance=args.imp_local
    ))

    execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'create_inhibited_network.sql')).format(
        result_name=scenery_name, 
        network_table=osm_table_name, 
        inhib_buffer=f'{scenery_name}_imp_buff', 
        impedance_buffer=f'{scenery_name}_imp_buff'
    ))

    # --- Stage 6: MERGING ---
    if callback: callback(6, "RUNNING")
    execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'create_full_network.sql')).format(
        result_name=internal_network_table, 
        ciclo=ciclo_table_name, 
        osm=scenery_name, 
        filters="", 
        bike_impedance=args.imp_bike
    ))

    if callback: callback(6, "DONE ✅")
    
    return scenery_name
