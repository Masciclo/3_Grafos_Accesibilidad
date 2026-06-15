import os
from infra.database import execute_query, read_sql_file
from infra.schema import SchemaGuard
from ui.components import diagnostic_handler

def run_topological_refactor(conn, args, osm_table_name, projects_table_name, location_prefix, internal_network_table, ciclo_table_name, sql_base_path, callback=None):
    """
    Task 18.4 (Iterative): Orchestrates the Refactoring by Assimilation sequence per Project ID.
    STRATEGY: Per-Project Autonomy with Pre-flight Greatest Overlap Resolver.
    FIX PHASE 19.5: Implemented Forced Topological Plugging to ensure 100% connectivity.
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

        # 2. Apply Assimilation & Innovation
        execute_query(conn, f"DELETE FROM {osm_table_name} WHERE id IN (SELECT parent_baseline_id FROM {assimilated_segments});")
        
        # Use ST_Dump to ensure LineString compatibility
        execute_query(conn, f"""
            INSERT INTO {osm_table_name} (geometry, highway, is_project, project_id, parent_baseline_id, impedance) 
            SELECT (ST_Dump(ST_MakeValid(geometry))).geom, 'project_assimilated', TRUE, project_id, parent_baseline_id, 0.5 
            FROM {assimilated_segments};
        """)
        
        execute_query(conn, f"""
            INSERT INTO {osm_table_name} (geometry, highway, is_project, project_id, impedance) 
            SELECT (ST_Dump(ST_MakeValid(p.geometry))).geom, 'project_innovation', TRUE, p.id, 0.5 
            FROM {projects_table_name} p 
            WHERE NOT EXISTS (SELECT 1 FROM {assimilated_segments} s WHERE s.project_id = p.id);
        """)

    # --- Stage 5.4: INHIBITION (Impedance Surface) ---
    if callback: callback(None, "ADVANCE_REFACTOR") 
    execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'create_impedance_buffers.sql')).format(result_table=f'{scenery_name}_imp_buff', table_name=osm_table_name, dist_buffer=args.buffer_size, high_impedance=args.imp_primary, medium_impedance=args.imp_secondary, low_impedance=args.imp_tertiary, else_impedance=args.imp_local))
    execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'create_inhibited_network.sql')).format(result_name=scenery_name, network_table=osm_table_name, inhib_buffer=f'{scenery_name}_imp_buff', impedance_buffer=f'{scenery_name}_imp_buff'))

    # --- Stage 6: MERGING ---
    if callback: callback(6, "RUNNING")
    execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'create_full_network.sql')).format(result_name=internal_network_table, ciclo=ciclo_table_name, osm=scenery_name, filters="", bike_impedance=args.imp_bike))

    # --- Stage 6.5: FINAL TOPOLOGICAL REPAIR (Phase 19.5 Fix) ---
    # We create standard topology ALWAYS to ensure source/target are populated for routing.
    diagnostic_handler.report("TOPOLOGY_FINAL", "INFO", "Building final routing topology...")
    execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'create_routing_topology.sql')).format(
        table=internal_network_table, 
        tolerance=0.1
    ))

    if args.projects_input:
        diagnostic_handler.report("NODALIZATION", "INFO", "Executing Project-specific Nodalization & Repair...")

        # Get list of unique projects
        with conn.cursor() as cur:
            cur.execute(f"SELECT DISTINCT project_id FROM {internal_network_table} WHERE is_project = TRUE")
            project_ids = [row[0] for row in cur.fetchall()]

        # Apply Forced Plugging per Project
        for pid in project_ids:
            if not pid: continue
            diagnostic_handler.report("PROJECT_PLUG", "INFO", f"Plugging project endpoints: {pid}")
            execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'plug_project_nodes.sql')).format(
                network_table=internal_network_table,
                mr_distance=mr_dist,
                pid=pid
            ))

    # Final Graph Hygiene (Always run to ensure clean edges)
    execute_query(conn, f"DELETE FROM {internal_network_table} WHERE ST_Length(geometry) < 0.5;")

    if callback: callback(6, "DONE ✅")
    
    return scenery_name
