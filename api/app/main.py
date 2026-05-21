# +Ciclo Engine: Demand-Based Routing Orchestrator 🚴‍♂️⚙️

import os
import sys
import argparse
import select
from dotenv import load_dotenv
import pandas as pd
import geopandas as gpd
from rich.console import Console
from rich.live import Live
from rich.prompt import Confirm

# Modular Imports
from ui.dashboard import PipelineUI, show_metadata_table, console
from ui.components import diagnostic_handler
from infra.database import create_conn, execute_query, read_sql_file, check_table_existence
from infra.ingestion import handle_path_argument, get_bbox_from_data, download_h3, extract_h3_grid_from_od
from infra.metadata import metadata_audit
from core import topology_refactor, routing, results

# Force UTF-8 for Emojis
sys.stdout.reconfigure(encoding='utf-8')

# Environment Configuration
load_dotenv()
DATABASE_NAME = os.getenv('DATABASE_NAME')
HOST = os.getenv('HOST')
PORT = os.getenv('PORT')
USER = os.getenv('DB_USER')
PASSWORD = os.getenv('DB_PASSWORD')
H3_LEVEL = os.getenv('H3_LEVEL')

sql_base_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'sql', 'common')
data_base_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data')

def data_pipeline(osm_input, ciclo_input, location_input, srid, od_input, census_input, args, 
                  internal_network_table, h3_table_name, osm_table_name, ciclo_table_name, 
                  projects_table_name, census_table_name, inhibitor_table_name, desinhibitor_table_name, scenario_prefix):
    
    ui = PipelineUI(location_input, srid, args=args)
    location_prefix = scenario_prefix.split('_')[0] # Usually the area abbreviation
    
    routing_task_id = None
    agg_task_id = None

    def ui_callback(phase_id, status, message=None, total=None):
        nonlocal routing_task_id, agg_task_id
        if phase_id:
            ui.update_phase(phase_id, status)
        
        if status == "ADVANCE_ROUTING":
            if routing_task_id is None:
                routing_task_id = ui.progress.add_task("[bold magenta]Routing Demand", total=total)
            ui.progress.advance(routing_task_id)
        
        if status == "ADVANCE_AGGREGATION":
            if agg_task_id is None:
                agg_task_id = ui.progress.add_task("[bold green]H3 Aggregation", total=6)
            ui.progress.advance(agg_task_id)
            if ui.progress.tasks[agg_task_id].finished:
                ui.progress.remove_task(agg_task_id)

        live.update(ui.get_dashboard_layout())

    # Establish connection
    conn = create_conn(DATABASE_NAME, HOST, PORT, USER, PASSWORD)

    # Stage 0: Pre-flight Audit
    console.print("[bold cyan]Stage 0: Pre-flight Audit[/]")
    if not diagnostic_handler.check_environment(conn):
        console.print("[bold red]Pre-flight audit failed. Check diagnostics above.[/]")
        return

    # Act 1: Living Landing (Confirmation Phase)
    if not args.force_yes:
        with Live(ui.get_landing_layout(), refresh_per_second=10, screen=False) as live:
            while True:
                live.update(ui.get_landing_layout())
                rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                if rlist:
                    sys.stdin.readline() 
                    break
    
    # Metadata Audit Phase
    census_columns = []
    if census_input and census_input.endswith('.parquet'):
        census_columns = pd.read_parquet(census_input, columns=[]).columns.tolist() 
    elif census_input and census_input.endswith('.geojson'):
        census_columns = gpd.read_file(census_input, rows=1).columns.tolist()
        
    od_columns = pd.read_csv(od_input, nrows=1).columns.tolist() if od_input else []
    
    census_mapping = metadata_audit("INE_CENSO_2024", census_columns)
    od_mapping = metadata_audit("SECTRA_EOD", od_columns)
    
    show_metadata_table(census_mapping, od_mapping)
    
    if not args.force_yes:
        if not Confirm.ask(f"\n[bold green]Metadata Mapped. Launch {location_input} ({args.scenario_id}) analysis?[/]"):
            console.print("[yellow]Aborted.[/]")
            return

    # Act 2: Pipeline Execution
    console.clear()
    try:
        with Live(ui.get_dashboard_layout(), refresh_per_second=10, screen=False) as live:
            
            # Stage 1: Ingestion
            ui_callback(1, "RUNNING")
            study_area_bbox = None
            if census_input: study_area_bbox = get_bbox_from_data(census_input, srid)
            elif od_input: study_area_bbox = get_bbox_from_data(od_input, srid)

            handle_path_argument('osm', osm_input, os.path.join(data_base_path, 'highways.geojson'), osm_table_name, location_input, 'LineString', srid, USER, PASSWORD, HOST, PORT, DATABASE_NAME, bbox=study_area_bbox)
            
            bike_source = ciclo_input if ciclo_input else 'osm'
            handle_path_argument('bike', bike_source, os.path.join(data_base_path, 'ciclo.geojson'), ciclo_table_name, location_input, 'LineString', srid, USER, PASSWORD, HOST, PORT, DATABASE_NAME, bbox=study_area_bbox)
            
            if not check_table_existence(conn, ciclo_table_name):
                with conn.cursor() as cursor:
                    cursor.execute(f"CREATE TABLE IF NOT EXISTS {ciclo_table_name} (geometry geometry(LineString, {srid}), impedance float)")
                diagnostic_handler.report("EMPTY_CICLO_CREATED", "INFO", "No bike infrastructure found. Created empty table.")
            
            if args.projects_input:
                handle_path_argument('projects', args.projects_input, None, projects_table_name, location_input, 'LineString', srid, USER, PASSWORD, HOST, PORT, DATABASE_NAME)
            
            if census_input:
                handle_path_argument('census', census_input, None, census_table_name, location_input, 'MultiPolygon', srid, USER, PASSWORD, HOST, PORT, DATABASE_NAME, bbox=study_area_bbox)
            ui_callback(1, "DONE ✅")
            
            # Stage 2: Topology Creation
            ui_callback(2, "RUNNING")
            execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'create_routing_topology.sql')).format(table=osm_table_name))
            base_components_table = f'{osm_table_name}_components'
            execute_query(conn, read_sql_file(os.path.join(sql_base_path, 'calculate_components.sql')).format(topo_name=f'{osm_table_name}_vertices_pgr', result_table=base_components_table, table_name=osm_table_name))
            diagnostic_handler.audit_network(conn, osm_table_name, base_components_table)
            ui_callback(2, "DONE ✅")

            # Stage 3: Grid Extraction
            ui_callback(3, "RUNNING")
            if od_input:
                extract_h3_grid_from_od(od_input, h3_table_name, srid, USER, PASSWORD, HOST, PORT, DATABASE_NAME)
            else:
                download_h3(osm_table_name, h3_table_name, srid, H3_LEVEL, USER, PASSWORD, HOST, PORT, DATABASE_NAME)
            ui_callback(3, "DONE ✅")

            # Stage 4: Snapping (Placeholder)
            ui.update_phase(4, "DONE ✅")

            # Stage 5 & 6: Topology Refactoring (Modularized)
            topology_refactor.run_topological_refactor(
                conn, args, osm_table_name, projects_table_name, location_prefix, 
                ciclo_table_name, internal_network_table, sql_base_path, callback=ui_callback
            )

            # Stage 7: Demand Routing (Modularized)
            routing.run_demand_routing(
                conn, args, internal_network_table, location_prefix, h3_table_name, 
                sql_base_path, USER, PASSWORD, HOST, PORT, DATABASE_NAME, callback=ui_callback
            )

            # Stage 8: Aggregation & Delta (Modularized)
            results.run_aggregation_and_delta(
                conn, args, location_prefix, scenario_prefix, internal_network_table, h3_table_name, 
                osm_table_name, ciclo_table_name, projects_table_name, census_table_name, 
                od_input, census_input, sql_base_path, callback=ui_callback
            )

            # Stage 9: QGIS Finalization (Modularized)
            results.finalize_qgis_layers(conn, scenario_prefix, internal_network_table, h3_table_name, ciclo_table_name, sql_base_path, callback=ui_callback)

            ui.completed = True
            ui.progress.update(ui.overall_task, completed=100)

    except Exception as e:
        if 'conn' in locals(): conn.rollback()
        diagnostic_handler.report("PIPELINE_CRASH", "ERROR", f"Critical Failure: {str(e)}")
        raise e
    finally:
        if args.cleanup and 'conn' in locals():
            diagnostic_handler.report("CLEANUP", "INFO", "Removing intermediate tables...")
            with conn.cursor() as cursor:
                tables = [osm_table_name, f"{osm_table_name}_vertices_pgr", f"{osm_table_name}_components", 
                          ciclo_table_name, projects_table_name, census_table_name, internal_network_table,
                          f"{internal_network_table}_vertices_pgr", f"{internal_network_table}_components",
                          h3_table_name, f"{scenario_prefix}_inhib_final", f"{scenario_prefix}_inhib_final_imp_buff"]
                for t in tables:
                    cursor.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
                conn.commit()
        console.print(ui.get_dashboard_layout())
    return 

def main():
    parser = argparse.ArgumentParser(description='+Ciclo: Advanced Demand-Based Routing Simulation')
    parser.add_argument("--location", dest="location", required=True, type=str)
    parser.add_argument("--scenario_id", dest="scenario_id", type=str, default="v1")
    parser.add_argument("--srid", dest="srid", required=True, type=str)
    parser.add_argument("--osm_input", dest="osm_input", type=str, default="osm")
    parser.add_argument("--ciclo_input", dest="ciclo_input", type=str)
    parser.add_argument("--od_input", dest="od_input", type=str)
    parser.add_argument("--census_input", dest="census_input", type=str)
    parser.add_argument("--projects_input", dest="projects_input", type=str)
    parser.add_argument("--reference_scenario", dest="reference_scenario", type=str)
    parser.add_argument("--yes", dest="force_yes", action="store_true")
    parser.add_argument("--cleanup", dest="cleanup", action="store_true")
    parser.add_argument("--buffer_size", dest="buffer_size", type=int, default=15)
    parser.add_argument("--imp_primary", dest="imp_primary", type=float, default=10.0)
    parser.add_argument("--imp_secondary", dest="imp_secondary", type=float, default=5.0)
    parser.add_argument("--imp_tertiary", dest="imp_tertiary", type=float, default=2.0)
    parser.add_argument("--imp_local", dest="imp_local", type=float, default=1.0)
    parser.add_argument("--imp_bike", dest="imp_bike", type=float, default=0.8)
    parser.add_argument("--inhibit", dest="inhibit", type=int, default=1)
    parser.add_argument("--disinhit", dest="disinhit", type=int, default=1)

    args = parser.parse_args()
    from infra.ingestion import create_abbreviation
    loc_pref = create_abbreviation(args.location)
    sce_pref = f"{loc_pref}_{args.scenario_id}"
    
    data_pipeline(args.osm_input, args.ciclo_input, args.location, args.srid, args.od_input, args.census_input, args, 
                  f"{sce_pref}_internal_net", f"{sce_pref}_internal_h3", f"{sce_pref}_osm_raw", f"{sce_pref}_ciclos", 
                  f"{sce_pref}_projects", f"{sce_pref}_census", f"{sce_pref}_inhibitor", f"{sce_pref}_desinhibitor", sce_pref)

if __name__=='__main__':
    main()
