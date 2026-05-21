import os
from infra.database import execute_query, read_sql_file
from infra.ingestion import handle_path_argument
from ui.components import diagnostic_handler

def run_demand_routing(conn, args, internal_network_table, location_prefix, h3_table_name, sql_base_path, USER, PASSWORD, HOST, PORT, DATABASE_NAME, callback=None):
    """
    Handles Stage 7 (Routing) of the pipeline, including snapping.
    """
    
    if callback: callback(7, "RUNNING", "H3-to-Node Snapping")
    
    scenario_prefix = f"{location_prefix}_{args.scenario_id}"
    full_components_table = f'{internal_network_table}_components'

    if args.od_input:
        # Re-calculate components on the final full network before snapping
        execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'create_routing_topology.sql')).format(table=internal_network_table))
        execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'calculate_components.sql')).format(topo_name=f'{internal_network_table}_vertices_pgr', result_table=full_components_table, table_name=internal_network_table))
        
        execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'snap_h3_to_network.sql')).format(location_prefix=scenario_prefix, network_table=internal_network_table, h3_table=h3_table_name, components_table=full_components_table))
        
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT count(*) FROM {scenario_prefix}_h3_to_node WHERE is_coverage_loss = false")
            snapped = cursor.fetchone()[0]
            cursor.execute(f"SELECT count(*) FROM {scenario_prefix}_h3_to_node")
            total = cursor.fetchone()[0]
            diagnostic_handler.report("SNAPPING_METRICS", "INFO", f"Coverage: {(snapped/total)*100:.1f}%")

    execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'create_routing_topology.sql')).format(table=internal_network_table))

    if args.od_input:
        if callback: callback(7, "RUNNING", "Routing Demand")
        
        od_table_name = f'{scenario_prefix}_od_matrix'
        handle_path_argument('od', args.od_input, None, od_table_name, args.location, 'None', args.srid, USER, PASSWORD, HOST, PORT, DATABASE_NAME)
        
        # --- NEW: Node Consolidation (Prevents 31x Inflation) ---
        diagnostic_handler.report("DEMAND_CONSOLIDATION", "INFO", "Consolidating H3 demand into unique graph nodes...")
        consolidated_table = f"{scenario_prefix}_node_demand_consolidated"
        execute_query(conn, f"DROP TABLE IF EXISTS {consolidated_table} CASCADE;")
        execute_query(conn, f"""
            CREATE TABLE {consolidated_table} AS
            SELECT 
                o.node_id as source_node,
                d.node_id as target_node,
                SUM(m.trips) as total_trips
            FROM {od_table_name} m
            JOIN {scenario_prefix}_h3_to_node o ON m.h3_origin = o.h3_index
            JOIN {scenario_prefix}_h3_to_node d ON m.h3_dest = d.h3_index
            WHERE o.is_coverage_loss = false AND d.is_coverage_loss = false
            GROUP BY o.node_id, d.node_id;
        """)

        execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'betweenness_init.sql')).format(network_table=internal_network_table))

        with conn.cursor() as cursor:
            cursor.execute(f"SELECT DISTINCT source_node FROM {consolidated_table}")
            origins = [row[0] for row in cursor.fetchall()]

        query_template_step = read_sql_file(os.path.join(sql_base_path, 'od_routing_step.sql'))
        
        # We handle the loop here, and use the callback for the progress bar if provided
        for origin_id in origins:
            execute_query(conn, query_template_step.format(
                network_table=internal_network_table, 
                location_prefix=scenario_prefix, 
                origin_id=origin_id, 
                edge_weight_column='cost', 
                directed='false'
            ))
            if callback: callback(None, "ADVANCE_ROUTING", total=len(origins))

        execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'demand_finalize.sql')).format(network_table=internal_network_table))

    if callback: callback(7, "DONE ✅")
    
    return full_components_table
