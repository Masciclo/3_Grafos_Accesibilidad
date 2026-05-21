import os
from infra.database import execute_query, read_sql_file, check_table_existence
from ui.components import diagnostic_handler

def run_aggregation_and_delta(conn, args, location_prefix, scenario_prefix, internal_network_table, h3_table_name, osm_table_name, ciclo_table_name, projects_table_name, census_table_name, od_input, census_input, sql_base_path, callback=None):
    """
    Handles Stage 8: H3 Aggregation and optional Delta calculation.
    """
    if callback: callback(8, "RUNNING", "Aggregation & Delta Calculation")

    # --- Attribute Parity Guard (#TS28) ---
    # Ensure all columns exist before any logic (including Delta) runs
    with conn.cursor() as cursor:
        cursor.execute(f"ALTER TABLE {h3_table_name} ADD COLUMN IF NOT EXISTS pop_total FLOAT DEFAULT 0")
        cursor.execute(f"ALTER TABLE {h3_table_name} ADD COLUMN IF NOT EXISTS od_flow FLOAT DEFAULT 0")
        cursor.execute(f"ALTER TABLE {h3_table_name} ADD COLUMN IF NOT EXISTS m_osm FLOAT DEFAULT 0")
        cursor.execute(f"ALTER TABLE {h3_table_name} ADD COLUMN IF NOT EXISTS m_project FLOAT DEFAULT 0")
        cursor.execute(f"ALTER TABLE {internal_network_table} ADD COLUMN IF NOT EXISTS od_flow NUMERIC DEFAULT 0")
        cursor.execute(f"ALTER TABLE {internal_network_table} ADD COLUMN IF NOT EXISTS is_project BOOLEAN DEFAULT FALSE")
        conn.commit()
    
    # --- Delta Engine (Line-Based) ---
    if args.reference_scenario:
        diagnostic_handler.report("DELTA_ENGINE", "INFO", f"Calculating Delta against: {args.reference_scenario}")
        delta_table_name = f"{scenario_prefix}_delta_network"
        
        # Priority: internal_net (raw), Fallback: network (finalized)
        internal_base = f"{location_prefix}_{args.reference_scenario}_internal_net"
        final_base = f"{location_prefix}_{args.reference_scenario}_network"
        
        baseline_network = None
        if check_table_existence(conn, internal_base):
            baseline_network = internal_base
        elif check_table_existence(conn, final_base):
            baseline_network = final_base
        
        if baseline_network:
            execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'calculate_delta_flow.sql')).format(
                result_table=delta_table_name,
                current_network=internal_network_table,
                baseline_network=baseline_network
            ))
            diagnostic_handler.report("DELTA_COMPLETE", "INFO", f"Delta layer created: {delta_table_name}")
        else:
            diagnostic_handler.report("DELTA_FAILED", "WARNING", f"No baseline network found for {args.reference_scenario}. Checked {internal_base} and {final_base}.")
    
    # Define aggregation queries
    full_components_table = f'{internal_network_table}_components'
    has_components = check_table_existence(conn, full_components_table)

    queries = [
        ('osm_data_to_h3.sql', {'osm_table': osm_table_name, 'h3_table': h3_table_name}),
        ('ciclo_data_to_h3.sql', {'ciclo_table': ciclo_table_name, 'h3_table': h3_table_name})
    ]
    
    if has_components:
        queries.append(('components_data_to_h3.sql', {'component_table': full_components_table, 'h3_table': h3_table_name}))
    
    if args.projects_input:
        queries.append(('projects_data_to_h3.sql', {'projects_table': projects_table_name, 'h3_table': h3_table_name}))
    
    if census_input:
        queries.append(('census_data_to_h3.sql', {'census_table': census_table_name, 'h3_table': h3_table_name}))
    
    if od_input:
        queries.append(('demand_data_to_h3.sql', {'network_table': internal_network_table, 'h3_table': h3_table_name}))

    for script, params in queries:
        execute_query(conn, read_sql_file(os.path.join(sql_base_path, script)).format(**params))
        if callback: callback(None, "ADVANCE_AGGREGATION")

    if callback: callback(8, "DONE ✅")

def finalize_qgis_layers(conn, scenario_prefix, internal_network_table, h3_table_name, ciclo_table_name, sql_base_path, callback=None):
    """
    Handles Stage 9: Flattening complex topology into clean output layers.
    """
    if callback: callback(9, "RUNNING", "QGIS Finalization")
    
    execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'finalize_qgis_layers.sql')).format(
        scenario_prefix=scenario_prefix,
        network_table=internal_network_table,
        h3_table=h3_table_name,
        ciclo_table=ciclo_table_name
    ))
    
    if callback: callback(9, "DONE ✅")
