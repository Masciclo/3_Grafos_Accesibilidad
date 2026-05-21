import os
from infra.database import execute_query, read_sql_file
from ui.components import diagnostic_handler

def run_topological_refactor(conn, args, osm_table_name, projects_table_name, location_prefix, ciclo_table_name, internal_network_table, sql_base_path, callback=None):
    """
    Handles Stage 5 (Inhibition/Injection) and Stage 6 (Merging) of the pipeline.
    """
    
    # --- Stage 5: Topology Refactoring & Injection ---
    if callback: callback(5, "RUNNING", "Generating Conflict AOIs")

    # Ensure is_project and impedance columns exist
    with conn.cursor() as cursor:
        cursor.execute(f"ALTER TABLE {osm_table_name} ADD COLUMN IF NOT EXISTS is_project BOOLEAN DEFAULT FALSE")
        cursor.execute(f"ALTER TABLE {osm_table_name} ADD COLUMN IF NOT EXISTS impedance FLOAT DEFAULT 1.0")
        conn.commit()

    # Spatial Matcher & Injection
    if args.projects_input:
        execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'spatial_match_projects.sql')).format(network_table=osm_table_name, projects_table=projects_table_name))
        
        # --- Snap & Shatter (Improved Connection Flexibility) ---
        diagnostic_handler.report("TOPOLOGY_CONNECT", "INFO", "Snapping project endpoints to network (15m tolerance)...")
        execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'snap_and_shatter_projects.sql')).format(network_table=osm_table_name, projects_table=projects_table_name, tolerance=15.0))
        
        execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'inject_projects.sql')).format(network_table=osm_table_name, projects_table=projects_table_name))
        
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {osm_table_name} WHERE is_project = TRUE")
            matched_count = cursor.fetchone()[0]
            diagnostic_handler.report("SPATIAL_MATCHER", "INFO", f"Infrastructure matched/injected: {matched_count} edges.")

    # Apply Parameterized Impedance & Buffering
    scenery_name = f'{location_prefix}_{args.scenario_id}_inhib_final'
    
    # Create Hierarchical Buffers (Conflicts)
    execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'create_impedance_buffers.sql')).format(
        result_table=f'{scenery_name}_imp_buff', 
        table_name=osm_table_name, 
        dist_buffer=args.buffer_size, 
        high_impedance=args.imp_primary, 
        medium_impedance=args.imp_secondary, 
        low_impedance=args.imp_tertiary, 
        else_impedance=args.imp_local
    ))

    # Splice the network based on buffers
    execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'create_inhibited_network.sql')).format(
        result_name=scenery_name, 
        network_table=osm_table_name, 
        inhib_buffer=f'{scenery_name}_imp_buff', 
        impedance_buffer=f'{scenery_name}_imp_buff'
    ))

    if callback: callback(5, "DONE ✅")

    # --- Stage 6: Merging ---
    if callback: callback(6, "RUNNING", "Intermodal Merging")
    
    execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'create_full_network.sql')).format(result_name=internal_network_table, ciclo=ciclo_table_name, osm=scenery_name, filters="", bike_impedance=args.imp_bike))

    if callback: callback(6, "DONE ✅")
    
    return scenery_name
