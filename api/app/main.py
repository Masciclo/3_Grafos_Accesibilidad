#Python main script to procces GIS data and obtain 
# several bike-path-oriented metrics of a given topology 


import pandas as pd
import geopandas as gpd
from dotenv import load_dotenv
import os
import argparse
import sys
import time
import select
import threading
from tqdm import tqdm
import utils
from rich.console import Console, Group
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from rich.prompt import Confirm

# Force UTF-8 for Emojis
sys.stdout.reconfigure(encoding='utf-8')
console = Console(force_terminal=True, color_system="truecolor")

class PipelineUI:
    def __init__(self, location, srid, args=None):
        self.location = location
        self.srid = srid
        self.args = args
        self.banner_path = os.path.join(os.path.dirname(__file__), "assets", "banner.json")
        self.animator = utils.BannerAnimator(self.banner_path)
        self.completed = False
        self.stop_animation = False
        
        self.phases = [
            {"id": 1, "name": "Data Ingestion", "status": "PENDING", "start": None, "end": None, "eta": "~1m"},
            {"id": 2, "name": "Topology Creation", "status": "PENDING", "start": None, "end": None, "eta": "~30s"},
            {"id": 3, "name": "Grid Extraction", "status": "PENDING", "start": None, "end": None, "eta": "~10s"},
            {"id": 4, "name": "H3 Snapping", "status": "PENDING", "start": None, "end": None, "eta": "~45s"},
            {"id": 5, "name": "Network Inhibition", "status": "PENDING", "start": None, "end": None, "eta": "~1m"},
            {"id": 6, "name": "Intermodal Merging", "status": "PENDING", "start": None, "end": None, "eta": "~20s"},
            {"id": 7, "name": "Demand Routing", "status": "PENDING", "start": None, "end": None, "eta": "Auto"},
            {"id": 8, "name": "H3 Aggregation", "status": "PENDING", "start": None, "end": None, "eta": "~1m"},
            {"id": 9, "name": "QGIS Finalization", "status": "PENDING", "start": None, "end": None, "eta": "~5s"}
        ]
        
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn()
        )
        self.overall_task = self.progress.add_task("[bold yellow]Overall Progress", total=100)

    def update_phase(self, phase_id, status="RUNNING"):
        now = time.time()
        for p in self.phases:
            if p["id"] == phase_id:
                p["status"] = status
                if status == "RUNNING": p["start"] = now
            elif p["id"] < phase_id and "DONE" not in p["status"]:
                p["status"] = "DONE ✅"
                p["end"] = now if p["start"] else None

    def format_time(self, seconds):
        if seconds is None: return "--"
        return f"{int(seconds)}s"

    def make_phase_table(self):
        table = Table(box=None, expand=True)
        table.add_column("#", style="dim", width=2)
        table.add_column("Stage", style="cyan", width=25)
        table.add_column("Status", justify="center", width=12)
        table.add_column("Elapsed", justify="right", style="dim")
        table.add_column("ETA", justify="right", style="dim")
        for p in self.phases:
            elapsed = self.format_time(p["end"] - p["start"]) if p["start"] and p["end"] else (self.format_time(time.time() - p["start"]) if p["start"] else "")
            style = "green" if "DONE" in p["status"] else "orange1" if "RUNNING" in p["status"] else "dim"
            status_text = "RUNNING 🏃" if p["status"] == "RUNNING" else p["status"]
            table.add_row(str(p["id"]), p["name"], f"[{style}]{p['status'] if 'DONE' in p['status'] else status_text}[/]", elapsed, p["eta"])
        return table

    def make_config_table(self):
        table = Table(title="[bold cyan]Pipeline Configuration", border_style="cyan", box=None)
        table.add_column("Parameter", style="bold blue")
        table.add_column("Value", style="white")
        if self.args:
            table.add_row("Location", self.location)
            table.add_row("Scenario", self.args.scenario_id)
            table.add_row("SRID", str(self.srid))
            table.add_row("Inhibition", "Enabled" if self.args.inhibit else "Disabled")
        return table

    def get_landing_layout(self):
        layout = Layout()
        layout.split_column(
            Layout(name="banner", ratio=4),
            Layout(name="middle", ratio=2),
            Layout(name="prompt", size=3)
        )
        layout["middle"].split_row(
            Layout(Panel(self.make_config_table(), border_style="cyan")),
            Layout(Panel(utils.diagnostic_handler.get_input_table(self.args.od_input if self.args else None, self.args.census_input if self.args else None, self.args.projects_input if self.args else None), border_style="blue"))
        )
        layout["banner"].update(Panel(Text(self.animator.get_next_frame(), justify="center", style="green"), title="[bold green]+CICLO SYSTEM READY", border_style="green", padding=(1,2)))
        layout["prompt"].update(Panel("[bold cyan]PRESS ENTER TO AUDIT METADATA...[/]", border_style="blink bold cyan", padding=(0,2)))
        return layout

    def get_dashboard_layout(self):
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="diagnostics", size=10),
            Layout(name="footer", size=3)
        )
        layout["header"].update(Panel(f"[bold white on blue] +CICLO ENGINE ACTIVE: {self.location} [/] [bold cyan] SCENARIO: {self.args.scenario_id} [/] [bold cyan] SRID: {self.srid} [/]", border_style="blue"))
        layout["body"].split_row(
            Layout(Panel(self.make_phase_table(), title="[bold]Stages", border_style="cyan"), ratio=2),
            Layout(Panel(self.progress, title="[bold]Process Monitoring", border_style="magenta"), ratio=1)
        )
        diag_list = []
        for d in utils.diagnostic_handler.diagnostics[-5:]:
            diag_list.append(Text.from_markup(f"{d['emoji']} [{d['color']} BOLD]{d['level']}:[/] {d['message']}"))
        if not diag_list: diag_list = [Text("Monitoring live telemetry...", style="dim")]
        layout["diagnostics"].update(Panel(Group(*diag_list), title="[bold yellow]Diagnostic Feed", border_style="yellow"))
        
        footer_msg = "[bold green]Pipeline Completed Successfully! 🎉[/]" if self.completed else "[italic]Engine processing architectural hooks...[/]"
        footer_style = "green" if self.completed else "dim"
        layout["footer"].update(Panel(footer_msg, border_style=footer_style))
        return layout

def show_metadata_table(census_map, od_map):
    table = Table(title="[bold green]Intelligent Metadata Mapping", border_style="green")
    table.add_column("Component", style="bold cyan")
    table.add_column("Parameter", style="blue")
    table.add_column("Detected Column", style="green")
    
    for k, v in census_map.items():
        table.add_row("Census (INE)", k, v)
    for k, v in od_map.items():
        table.add_row("Demand (SECTRA)", k, v)
        
    console.print(Panel(table, border_style="green"))

#load env variables
load_dotenv()
DATABASE_NAME = os.getenv('DATABASE_NAME')
HOST = os.getenv('HOST')
PORT = os.getenv('PORT')
USER = os.getenv('DB_USER')
PASSWORD = os.getenv('DB_PASSWORD')
H3_LEVEL = os.getenv('H3_LEVEL')
RADIUS_ACCESS = os.getenv('RADIUS_ACCESS')
HIGH_IMPEDANCE = os.getenv('HIGH_IMPEDANCE')
MEDIUM_IMPEDANCE = os.getenv('MEDIUM_IMPEDANCE')
LOW_IMPEDANCE = os.getenv('LOW_IMPEDANCE')
ELSE_IMPEDANCE = os.getenv('ELSE_IMPEDANCE')

conn = utils.create_conn(DATABASE_NAME,HOST,PORT,USER,PASSWORD)
sql_base_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'sql-scripts')
data_base_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data')

def data_pipeline(osm_input, ciclo_input, location_input, srid, od_input, census_input, args, internal_network_table, h3_table_name, osm_table_name, ciclo_table_name, projects_table_name, census_table_name, inhibitor_table_name, desinhibitor_table_name, scenario_prefix):
    
    ui = PipelineUI(location_input, srid, args=args)
    location_prefix = utils.create_abbreviation(location_input)

    # Act 1: Living Landing
    console.clear()
    if not args.force_yes:
        with Live(ui.get_landing_layout(), refresh_per_second=10, screen=False) as live:
            while True:
                live.update(ui.get_landing_layout())
                rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                if rlist:
                    sys.stdin.readline() 
                    break
    
    # --- Phase 5.3: Intelligent Metadata Audit ---
    census_columns = []
    if census_input and census_input.endswith('.parquet'):
        census_columns = pd.read_parquet(census_input, columns=[]).columns.tolist() # fast head
    elif census_input and census_input.endswith('.geojson'):
        census_columns = gpd.read_file(census_input, rows=1).columns.tolist()
        
    od_columns = pd.read_csv(od_input, nrows=1).columns.tolist() if od_input else []
    
    census_mapping = utils.diagnostic_handler.metadata_audit("INE_CENSO_2024", census_columns)
    od_mapping = utils.diagnostic_handler.metadata_audit("SECTRA_EOD", od_columns)
    
    show_metadata_table(census_mapping, od_mapping)
    
    if not args.force_yes:
        if not Confirm.ask(f"\n[bold green]Metadata Mapped. Launch {location_input} ({args.scenario_id}) analysis?[/]"):
            console.print("[yellow]Aborted.[/]")
            return

    # Act 2: Dashboard
    console.clear()
    with Live(ui.get_dashboard_layout(), refresh_per_second=10, screen=False) as live:
        
        # Stage 1: Ingestion
        ui.update_phase(1, "RUNNING")
        ingest_task = ui.progress.add_task("[bold orange1]Data Ingestion", total=100)
        live.update(ui.get_dashboard_layout())

        osm_base_path = os.path.join(data_base_path, 'highways.geojson')
        ciclo_base_path = os.path.join(data_base_path, 'ciclo.geojson')
        
        study_area_bbox = None
        if census_input: study_area_bbox = utils.get_bbox_from_data(census_input, srid)
        elif od_input: study_area_bbox = utils.get_bbox_from_data(od_input, srid)
        ui.progress.update(ingest_task, completed=10)

        # OSM Ingestion
        utils.handle_path_argument('osm', osm_input, osm_base_path, osm_table_name, location_input, 'LineString', srid, USER, PASSWORD, HOST, PORT, DATABASE_NAME, bbox=study_area_bbox)
        ui.progress.update(ingest_task, completed=50)
        
        # Bike Ingestion
        # Logic: If no input, default to 'osm' to capture existing cycleways. 
        # If that fails or is empty, create empty table to avoid Stage 6 crashes.
        bike_source = ciclo_input if ciclo_input else 'osm'
        utils.handle_path_argument('bike', bike_source, ciclo_base_path, ciclo_table_name, location_input, 'LineString', srid, USER, PASSWORD, HOST, PORT, DATABASE_NAME, bbox=study_area_bbox)
        
        if not utils.check_table_existence(conn, ciclo_table_name):
            with conn.cursor() as cursor:
                cursor.execute(f"CREATE TABLE IF NOT EXISTS {ciclo_table_name} (geometry geometry(LineString, {srid}), impedance float)")
            utils.diagnostic_handler.report("EMPTY_CICLO_CREATED", "INFO", "No bike infrastructure found. Created empty table for pipeline integrity.")
        
        ui.progress.update(ingest_task, completed=70)

        # Projects Ingestion (Phase 5)
        if args.projects_input:
            utils.handle_path_argument('projects', args.projects_input, None, projects_table_name, location_input, 'LineString', srid, USER, PASSWORD, HOST, PORT, DATABASE_NAME)
        ui.progress.update(ingest_task, completed=85)

        # Census Ingestion (Phase 5)
        if census_input:
            utils.handle_path_argument('census', census_input, None, census_table_name, location_input, 'MultiPolygon', srid, USER, PASSWORD, HOST, PORT, DATABASE_NAME, bbox=study_area_bbox)
        ui.progress.update(ingest_task, completed=100)
        ui.progress.remove_task(ingest_task)
        
        # Stage 2: Topology
        ui.update_phase(2, "RUNNING")
        ui.progress.update(ui.overall_task, completed=12)
        topo_task = ui.progress.add_task("[bold orange1]Topology & LCC", total=3)
        live.update(ui.get_dashboard_layout())
        
        utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'create_routing_topology.sql')).format(table=osm_table_name))
        ui.progress.advance(topo_task)
        
        base_components_table = f'{osm_table_name}_components'
        utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'calculate_components.sql')).format(topo_name=f'{osm_table_name}_vertices_pgr', result_table=base_components_table, table_name=osm_table_name))
        ui.progress.advance(topo_task)
        
        utils.diagnostic_handler.audit_network(conn, osm_table_name, base_components_table)
        ui.progress.update(topo_task, completed=3)
        ui.progress.remove_task(topo_task)

        # Stage 3: Grid
        ui.update_phase(3, "RUNNING")
        ui.progress.update(ui.overall_task, completed=25)
        grid_task = ui.progress.add_task("[bold blue]Grid Synchronization", total=1)
        live.update(ui.get_dashboard_layout())
        
        if od_input:
            count = utils.extract_h3_grid_from_od(od_input, h3_table_name.replace("_h3",""), srid, USER, PASSWORD, HOST, PORT, DATABASE_NAME)
            utils.diagnostic_handler.report("H3_GRID_SYNC", "INFO", f"Grid Match: {count} cells.")
        else:
            utils.download_h3(h3_table_name.replace("_h3",""),srid,H3_LEVEL,USER,PASSWORD,HOST,PORT,DATABASE_NAME)
        ui.progress.update(grid_task, completed=1)
        ui.progress.remove_task(grid_task)

        # Stage 4: Snapping (Placeholder - Moved to Stage 7)
        ui.update_phase(4, "RUNNING")
        ui.progress.update(ui.overall_task, completed=37)
        ui.update_phase(4, "DONE ✅")

        # Stage 5: Inhibition (Parameterized)
        ui.update_phase(5, "RUNNING")
        ui.progress.update(ui.overall_task, completed=50)
        inhib_task = ui.progress.add_task("[bold orange1]Generating Conflict AOIs", total=3)
        live.update(ui.get_dashboard_layout())

        # --- SRID Safety Check (#TS26) ---
        if srid == "4326" or srid == "4269":
            utils.diagnostic_handler.report("SRID_KILLER_DETECTED", "ERROR", "Geographic SRID (degrees) detected. Spatial Matcher requires a Metric SRID (meters). Aborting.")
            return
        
        # Ensure is_project column exists for Stage 5 surgery parity
        with conn.cursor() as cursor:
            cursor.execute(f"ALTER TABLE {osm_table_name} ADD COLUMN IF NOT EXISTS is_project BOOLEAN DEFAULT FALSE")
            conn.commit()

        # Spatial Matcher & Injection (Phase 5 Logic)
        if args.projects_input:
            utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'spatial_match_projects.sql')).format(network_table=osm_table_name, projects_table=projects_table_name))
            utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'inject_projects.sql')).format(network_table=osm_table_name, projects_table=projects_table_name))
            
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) FROM {osm_table_name} WHERE is_project = TRUE")
                matched_count = cursor.fetchone()[0]
                utils.diagnostic_handler.report("SPATIAL_MATCHER", "INFO", f"Infrastructure matched/injected: {matched_count} edges.")
        
        ui.progress.advance(inhib_task)

        # Apply Parameterized Impedance & Buffering
        scenery_name = f'{location_prefix}_{args.scenario_id}_inhib_final'
        
        # Create Hierarchical Buffers (Conflicts)
        utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'create_impedance_buffers.sql')).format(
            result_table=f'{scenery_name}_imp_buff', 
            table_name=osm_table_name, 
            dist_buffer=args.buffer_size, 
            high_impedance=args.imp_primary, 
            medium_impedance=args.imp_secondary, 
            low_impedance=args.imp_tertiary, 
            else_impedance=args.imp_local
        ))
        ui.progress.advance(inhib_task)

        # Splice the network based on buffers
        utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'create_inhibited_network.sql')).format(
            result_name=scenery_name, 
            network_table=osm_table_name, 
            inhib_buffer=f'{scenery_name}_imp_buff', 
            impedance_buffer=f'{scenery_name}_imp_buff'
        ))
        ui.progress.update(inhib_task, completed=3)
        ui.progress.remove_task(inhib_task)

        # Stage 6: Merging
        ui.update_phase(6, "RUNNING")
        ui.progress.update(ui.overall_task, completed=62)
        live.update(ui.get_dashboard_layout())
        
        utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'create_full_network.sql')).format(result_name=internal_network_table, ciclo=ciclo_table_name, osm=scenery_name, filters="", bike_impedance=args.imp_bike))

        # Stage 7: Routing
        ui.update_phase(7, "RUNNING")
        ui.progress.update(ui.overall_task, completed=75)
        live.update(ui.get_dashboard_layout())

        # Snapping (Moved from Stage 4)
        if od_input:
            snap_task = ui.progress.add_task("[bold blue]H3-to-Node Snapping", total=1)
            # Re-calculate components on the final full network before snapping
            full_components_table = f'{internal_network_table}_components'
            utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'create_routing_topology.sql')).format(table=internal_network_table))
            utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'calculate_components.sql')).format(topo_name=f'{internal_network_table}_vertices_pgr', result_table=full_components_table, table_name=internal_network_table))
            
            utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'snap_h3_to_network.sql')).format(location_prefix=f"{location_prefix}_{args.scenario_id}", network_table=internal_network_table, h3_table=h3_table_name, components_table=full_components_table))
            
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT count(*) FROM {location_prefix}_{args.scenario_id}_h3_to_node WHERE is_coverage_loss = false")
                snapped = cursor.fetchone()[0]
                cursor.execute(f"SELECT count(*) FROM {location_prefix}_{args.scenario_id}_h3_to_node")
                total = cursor.fetchone()[0]
                utils.diagnostic_handler.report("SNAPPING_METRICS", "INFO", f"Coverage: {(snapped/total)*100:.1f}%")
            ui.progress.update(snap_task, completed=1)
            ui.progress.remove_task(snap_task)
        
        utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'create_routing_topology.sql')).format(table=internal_network_table))

        if od_input:
            od_table_name = f'{location_prefix}_{args.scenario_id}_od_matrix'
            utils.handle_path_argument('od', od_input, None, od_table_name, location_input, 'None', srid, USER, PASSWORD, HOST, PORT, DATABASE_NAME)
            utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'calculate_od_weighted_betweenness.sql')).format(location_prefix=f"{location_prefix}_{args.scenario_id}", od_matrix_table=od_table_name))
            utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'betweenness_init.sql')).format(network_table=internal_network_table))

            with conn.cursor() as cursor:
                cursor.execute(f"SELECT DISTINCT source_node FROM {location_prefix}_{args.scenario_id}_node_demand")
                origins = [row[0] for row in cursor.fetchall()]

            query_template_step = utils.read_sql_file(os.path.join(sql_base_path, 'od_routing_step.sql'))
            routing_task = ui.progress.add_task("[bold magenta]Routing Demand", total=len(origins))
            ui.phases[6]["eta"] = f"~{int(len(origins)/10)}s" 
            for origin_id in origins:
                utils.execute_query(conn, query_template_step.format(network_table=internal_network_table, location_prefix=f"{location_prefix}_{args.scenario_id}", origin_id=origin_id, edge_weight_column='cost', directed='false'))
                ui.progress.advance(routing_task)
                live.update(ui.get_dashboard_layout())

            utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'demand_finalize.sql')).format(network_table=internal_network_table))
            ui.progress.remove_task(routing_task)

        # Stage 8: Aggregation
        ui.update_phase(8, "RUNNING")
        ui.progress.update(ui.overall_task, completed=88)
        agg_task = ui.progress.add_task("[bold green]H3 Aggregation", total=6)
        live.update(ui.get_dashboard_layout())

        # --- Attribute Parity Guard (#TS28) ---
        # Ensure all columns exist for Stage 9 even if stages were skipped
        with conn.cursor() as cursor:
            # H3 Table Guards
            cursor.execute(f"ALTER TABLE {h3_table_name} ADD COLUMN IF NOT EXISTS pop_total FLOAT DEFAULT 0")
            cursor.execute(f"ALTER TABLE {h3_table_name} ADD COLUMN IF NOT EXISTS od_flow FLOAT DEFAULT 0")
            cursor.execute(f"ALTER TABLE {h3_table_name} ADD COLUMN IF NOT EXISTS m_osm FLOAT DEFAULT 0")
            cursor.execute(f"ALTER TABLE {h3_table_name} ADD COLUMN IF NOT EXISTS m_project FLOAT DEFAULT 0")
            # Network Table Guards
            cursor.execute(f"ALTER TABLE {internal_network_table} ADD COLUMN IF NOT EXISTS od_flow NUMERIC DEFAULT 0")
            cursor.execute(f"ALTER TABLE {internal_network_table} ADD COLUMN IF NOT EXISTS is_project BOOLEAN DEFAULT FALSE")
            conn.commit()
        
        queries = [
            ('osm_data_to_h3.sql', {'osm_table': osm_table_name, 'h3_table': h3_table_name}),
            ('ciclo_data_to_h3.sql', {'ciclo_table': ciclo_table_name, 'h3_table': h3_table_name}),
            ('components_data_to_h3.sql', {'component_table': full_components_table if od_input else 'None', 'h3_table': h3_table_name})
        ]
        
        if args.projects_input:
            queries.append(('projects_data_to_h3.sql', {'projects_table': projects_table_name, 'h3_table': h3_table_name}))
        
        if census_input:
            queries.append(('census_data_to_h3.sql', {'census_table': census_table_name, 'h3_table': h3_table_name}))
        
        if od_input:
            queries.append(('demand_data_to_h3.sql', {'network_table': internal_network_table, 'h3_table': h3_table_name}))

        for script, params in queries:
            utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, script)).format(**params))
            ui.progress.advance(agg_task)
            live.update(ui.get_dashboard_layout())

        # Stage 9: QGIS Finalization
        ui.update_phase(9, "RUNNING")
        utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'finalize_qgis_layers.sql')).format(
            scenario_prefix=scenario_prefix,
            network_table=internal_network_table,
            h3_table=h3_table_name
        ))

        # Completion State
        ui.completed = True
        ui.update_phase(9, "DONE ✅")
        ui.progress.update(ui.overall_task, completed=100)
        ui.progress.remove_task(agg_task)
        live.update(ui.get_dashboard_layout())

    # Persistent final print
    console.print(ui.get_dashboard_layout())
    return 

def main():
    parser = argparse.ArgumentParser(description='+Ciclo: Advanced Demand-Based Routing Simulation')
    
    # --- Scenario & Data Inputs ---
    parser.add_argument("--location", dest="location", required=True, type=str, help="Location name (e.g. Valdivia, Chile)")
    parser.add_argument("--scenario_id", dest="scenario_id", type=str, default="v1", help="Unique identifier for this scenario branching")
    parser.add_argument("--srid", dest="srid", required=True, type=str, help="Metric SRID for calculations (e.g. 32718)")
    parser.add_argument("--osm_input", dest="osm_input", type=str, default="osm", help="OSM network source")
    parser.add_argument("--ciclo_input", dest="ciclo_input", type=str, help="Local bike path GeoJSON (optional)")
    parser.add_argument("--od_input", dest="od_input", type=str, help="OD matrix CSV path")
    parser.add_argument("--census_input", dest="census_input", type=str, help="Census H3/Parquet path")
    parser.add_argument("--projects_input", dest="projects_input", type=str, help="Proposed GeoJSON projects path")
    parser.add_argument("--yes", dest="force_yes", action="store_true", help="Bypass interactive gates")

    # --- Simulation Tuning (Phase 6) ---
    parser.add_argument("--buffer_size", dest="buffer_size", type=int, default=15, help="Radius of influence for road types (meters)")
    parser.add_argument("--imp_primary", dest="imp_primary", type=float, default=10.0, help="Penalty for Primary roads")
    parser.add_argument("--imp_secondary", dest="imp_secondary", type=float, default=5.0, help="Penalty for Secondary roads")
    parser.add_argument("--imp_tertiary", dest="imp_tertiary", type=float, default=2.0, help="Penalty for Tertiary roads")
    parser.add_argument("--imp_local", dest="imp_local", type=float, default=1.0, help="Penalty for Local roads")
    parser.add_argument("--imp_bike", dest="imp_bike", type=float, default=0.8, help="Benefit of dedicated bike lanes")

    # Legacy / Internal
    parser.add_argument("--inhibit", dest="inhibit", type=int, default=1)
    parser.add_argument("--disinhit", dest="disinhit", type=int, default=1)

    args = parser.parse_args()

    # Define unified scenario-driven names
    location_prefix = utils.create_abbreviation(args.location)
    scenario_prefix = f"{location_prefix}_{args.scenario_id}"
    
    # Master tables (The ones the user sees in QGIS) - Defined later in Stage 9
    
    # Intermediate / Internal names (Clean for Stage 1-8)
    osm_table_name = f"{scenario_prefix}_osm_raw"
    ciclo_table_name = f"{scenario_prefix}_ciclos"
    projects_table_name = f"{scenario_prefix}_projects"
    census_table_name = f"{scenario_prefix}_census"
    inhibitor_table_name = f"{scenario_prefix}_inhibitor"
    desinhibitor_table_name = f"{scenario_prefix}_desinhibitor"
    internal_network_table = f"{scenario_prefix}_internal_net" # New name for internal topology
    h3_table_name = f"{scenario_prefix}_internal_h3" # New name for internal grid

    data_pipeline(args.osm_input, args.ciclo_input, args.location, args.srid, 
                  args.od_input, args.census_input, args, 
                  internal_network_table, h3_table_name, osm_table_name, ciclo_table_name, 
                  projects_table_name, census_table_name, inhibitor_table_name, desinhibitor_table_name, scenario_prefix)

if __name__=='__main__':
    main()
