import os
import traceback
import geopandas as gpd
from sqlalchemy import create_engine, text
from infra.database import execute_query, read_sql_file, check_table_existence
from infra.schema import SchemaGuard
from ui.components import diagnostic_handler
from core.academic_maps import AcademicMapGenerator

def run_aggregation_and_delta(conn, args, location_prefix, scenario_prefix, internal_network_table, h3_table_name, osm_table_name, ciclo_table_name, projects_table_name, census_table_name, od_input, census_input, sql_base_path, srid, ma_distance=7.0, callback=None):
    """
    Handles Stage 8: H3 Aggregation and optional Delta calculation.
    """
    if callback: callback(8, "RUNNING", "Aggregation & Delta Calculation")

    SchemaGuard.ensure_h3_parity(conn, h3_table_name)
    SchemaGuard.ensure_network_parity(conn, internal_network_table)
    
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
            execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'calculate_delta_flow.sql')).format(
                result_table=delta_table_name,
                current_network=internal_network_table,
                baseline_network=baseline_network,
                ma_distance=ma_distance
            ))
            diagnostic_handler.report("DELTA_COMPLETE", "INFO", f"Delta layer created: {delta_table_name}")
        else:
            diagnostic_handler.report("DELTA_FAILED", "WARNING", f"No baseline network found for {args.reference_scenario}.")
    
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
        queries.append(('census_data_to_h3.sql', {'census_table': census_table_name, 'h3_table': h3_table_name, 'srid': srid}))
    if od_input:
        queries.append(('demand_data_to_h3.sql', {'network_table': internal_network_table, 'h3_table': h3_table_name}))

    for script, params in queries:
        execute_query(conn, read_sql_file(os.path.join(sql_base_path, script)).format(**params))
        if callback: callback(None, "ADVANCE_AGGREGATION")

    if callback: callback(8, "DONE ✅")


def finalize_qgis_layers(conn, scenario_prefix, internal_network_table, h3_table_name, ciclo_table_name, sql_base_path, args, callback=None, census_table_name=None, osm_table_name=None, zones_table_name=None, city_key=None):
    """
    Handles Stage 9: Finalization and Academic Mapping with PCR Metrics.
    """
    if callback: callback(9, "RUNNING", "QGIS Finalization")
    
    execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'finalize_qgis_layers.sql')).format(
        scenario_prefix=scenario_prefix,
        network_table=internal_network_table,
        h3_table=h3_table_name,
        ciclo_table=ciclo_table_name
    ))

    if zones_table_name:
        try:
            execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'calculate_mcp_flag.sql')).format(
                scenario_prefix=scenario_prefix, zones_table=zones_table_name, h3_table=h3_table_name
            ))
        except Exception: pass

    # --- Phase 17: Denominator Extraction for PCR ---
    total_trips = 1.0
    try:
        with conn.cursor() as cur:
            # Denominator: Successfully routed trips for city-wide normalization
            cur.execute(f"SELECT SUM(trips) FROM {scenario_prefix}_od_matrix")
            total_trips = float(cur.fetchone()[0] or 1.0)
            diagnostic_handler.report("METRICS_DENOMINATOR", "INFO", f"City-wide demand for PCR: {int(total_trips)} trips.")
    except Exception as e:
        diagnostic_handler.report("PCR_FAILED", "WARNING", f"Demand extraction failed: {e}")

    # --- Academic Mapping ---
    diagnostic_handler.report("MAPPING", "INFO", f"Generating synchronized dashboard for {scenario_prefix}...")
    try:
        user, password, host, port, db = os.getenv('DB_USER'), os.getenv('DB_PASSWORD'), os.getenv('HOST'), os.getenv('PORT'), os.getenv('DATABASE_NAME')
        engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{db}')
        
        output_loc = city_key if city_key else scenario_prefix.split('_')[0]
        generator = AcademicMapGenerator(output_dir=f"data/{output_loc}/out/maps")
        
        net_gdf = gpd.read_postgis(f"SELECT * FROM {scenario_prefix}_network", engine, geom_col='geometry')
        mask_col = 'participating_in_analysis'
        mcp_gdf = net_gdf[net_gdf[mask_col] == True] if mask_col in net_gdf.columns else net_gdf
        master_bbox = mcp_gdf.total_bounds
        
        generator.generate_impedance_map(net_gdf, scenario_prefix, bbox=master_bbox)
        
        p_maps = []
        # Map 1: Baseline
        if args.reference_scenario:
            try:
                city_alias = scenario_prefix.split('_')[0]
                base_table = f"{city_alias}_{args.reference_scenario}_network"
                base_gdf = gpd.read_postgis(f"SELECT * FROM {base_table}", engine, geom_col='geometry')
                if not base_gdf.empty:
                    p_maps.append(generator.generate_flow_map(base_gdf, base_table, type="baseline", bbox=master_bbox, total_trips=total_trips))
                else: p_maps.append(None)
            except Exception: p_maps.append(None)
        else: p_maps.append(None)

        # Map 2: Segment-wise Performance
        p_maps.append(generator.generate_project_performance_map(net_gdf, scenario_prefix, bbox=master_bbox, total_trips=total_trips))
        # Map 3: Scenario Flow
        p_maps.append(generator.generate_flow_map(net_gdf, scenario_prefix, type="flow", bbox=master_bbox, total_trips=total_trips))
        # Map 4: Delta
        delta_table = f"{scenario_prefix}_delta_network"
        if check_table_existence(conn, delta_table):
            delta_gdf = gpd.read_postgis(f"SELECT * FROM {delta_table}", engine, geom_col='geometry')
            p_maps.append(generator.generate_delta_sigma_map(delta_gdf, scenario_prefix, bbox=master_bbox, context_gdf=net_gdf))
        else:
            p_maps.append(None)

        if args.reference_scenario and p_maps[0] is not None:
            generator.compile_report(scenario_prefix, p_maps)

    except Exception as e:
        diagnostic_handler.report("MAPPING_FAILED", "ERROR", f"Mapping failed: {e} | {traceback.format_exc().splitlines()[-1]}")

    if callback: callback(9, "DONE ✅")
