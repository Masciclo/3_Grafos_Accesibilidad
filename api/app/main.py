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
        
        self.phases = [
            {"id": 1, "name": "Data Ingestion", "status": "PENDING", "start": None, "end": None, "eta": "~1m"},
            {"id": 2, "name": "Topology Creation", "status": "PENDING", "start": None, "end": None, "eta": "~30s"},
            {"id": 3, "name": "Grid Extraction", "status": "PENDING", "start": None, "end": None, "eta": "~10s"},
            {"id": 4, "name": "H3 Snapping", "status": "PENDING", "start": None, "end": None, "eta": "~45s"},
            {"id": 5, "name": "Network Inhibition", "status": "PENDING", "start": None, "end": None, "eta": "~1m"},
            {"id": 6, "name": "Intermodal Merging", "status": "PENDING", "start": None, "end": None, "eta": "~20s"},
            {"id": 7, "name": "Demand Routing", "status": "PENDING", "start": None, "end": None, "eta": "Auto"},
            {"id": 8, "name": "H3 Aggregation", "status": "PENDING", "start": None, "end": None, "eta": "~1m"}
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
            Layout(Panel(utils.diagnostic_handler.get_input_table(self.args.od_input if self.args else None, self.args.census_input if self.args else None), border_style="blue"))
        )
        layout["banner"].update(Panel(Text(self.animator.get_next_frame(), justify="center", style="green"), title="[bold green]+CICLO SYSTEM READY", border_style="green", padding=(1,2)))
        layout["prompt"].update(Panel("[bold cyan]PRESS ENTER TO LAUNCH ANALYSIS...[/]", border_style="blink bold cyan", padding=(0,2)))
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

def data_pipeline(osm_input, ciclo_input, location_input, srid, inhibit, inhibitor_input, buffer_inhib, disinhit, disinhitor_input, buffer_desinhib, proye, ci_o_cr, op_ci, od_input, census_input, args, network_table_name, h3_table_name, osm_table_name, ciclo_table_name, inhibitor_table_name, desinhibitor_table_name):
    
    if not utils.diagnostic_handler.validate_inputs(od_input, census_input):
        console.print("[bold red]Critical Error: Input validation failed.[/]")
        sys.exit(1)

    ui = PipelineUI(location_input, srid, args=args)
    location_prefix = utils.create_abbreviation(location_input) # Fixed Scope

    # Act 1: Living Landing (Non-blocking Animation + Input)
    console.clear()
    with Live(ui.get_landing_layout(), refresh_per_second=10, screen=False) as live:
        while True:
            live.update(ui.get_landing_layout())
            rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
            if rlist:
                sys.stdin.readline() 
                break

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
        utils.handle_path_argument('bike', ciclo_input, ciclo_base_path, ciclo_table_name, location_input, 'LineString', srid, USER, PASSWORD, HOST, PORT, DATABASE_NAME)
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

        # Stage 4: Snapping
        ui.update_phase(4, "RUNNING")
        ui.progress.update(ui.overall_task, completed=37)
        snap_task = ui.progress.add_task("[bold blue]H3-to-Node Snapping", total=1)
        live.update(ui.get_dashboard_layout())
        
        if od_input:
            utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'snap_h3_to_network.sql')).format(location_prefix=f"{location_prefix}_{args.scenario_id}", network_table=osm_table_name, h3_table=h3_table_name, components_table=base_components_table))
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT count(*) FROM {location_prefix}_{args.scenario_id}_h3_to_node WHERE is_coverage_loss = false")
                snapped = cursor.fetchone()[0]
                cursor.execute(f"SELECT count(*) FROM {location_prefix}_{args.scenario_id}_h3_to_node")
                total = cursor.fetchone()[0]
                utils.diagnostic_handler.report("SNAPPING_METRICS", "INFO", f"Coverage: {(snapped/total)*100:.1f}%")
        ui.progress.update(snap_task, completed=1)
        ui.progress.remove_task(snap_task)

        # Stage 5: Inhibition
        ui.update_phase(5, "RUNNING")
        ui.progress.update(ui.overall_task, completed=50)
        inhib_task = ui.progress.add_task("[bold orange1]Network Inhibition", total=3)
        live.update(ui.get_dashboard_layout())
        
        utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'modify_impedance.sql')).format(table_name=osm_table_name))
        ui.progress.advance(inhib_task)
        
        if inhibit:
            scenery_name = f'{location_prefix}_{args.scenario_id}_inhib_final'
            utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'create_impedance_buffers.sql')).format(result_table=f'{scenery_name}_imp_buff', table_name=osm_table_name, dist_buffer=buffer_inhib, high_impedance=HIGH_IMPEDANCE, medium_impedance=MEDIUM_IMPEDANCE, low_impedance=LOW_IMPEDANCE, else_impedance=ELSE_IMPEDANCE))
            ui.progress.advance(inhib_task)
            utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'create_inhibited_network.sql')).format(result_name=scenery_name, network_table=osm_table_name, inhib_buffer=f'{scenery_name}_imp_buff', impedance_buffer=f'{scenery_name}_imp_buff'))
        else:
            scenery_name = osm_table_name
        ui.progress.update(inhib_task, completed=3)
        ui.progress.remove_task(inhib_task)

        # Stage 6: Merging
        ui.update_phase(6, "RUNNING")
        ui.progress.update(ui.overall_task, completed=62)
        live.update(ui.get_dashboard_layout())
        
        utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'create_full_network.sql')).format(result_name=network_table_name, ciclo=ciclo_table_name, osm=scenery_name, filters=""))

        # Stage 7: Routing
        ui.update_phase(7, "RUNNING")
        ui.progress.update(ui.overall_task, completed=75)
        live.update(ui.get_dashboard_layout())
        
        utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'create_routing_topology.sql')).format(table=network_table_name))

        if od_input:
            od_table_name = f'{location_prefix}_{args.scenario_id}_od_matrix'
            utils.upload_csv_to_db(od_input, od_table_name, USER, PASSWORD, HOST, PORT, DATABASE_NAME)
            utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'calculate_od_weighted_betweenness.sql')).format(location_prefix=f"{location_prefix}_{args.scenario_id}", od_matrix_table=od_table_name))
            utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'betweenness_init.sql')).format(network_table=network_table_name))

            with conn.cursor() as cursor:
                cursor.execute(f"SELECT DISTINCT source_node FROM {location_prefix}_{args.scenario_id}_node_demand")
                origins = [row[0] for row in cursor.fetchall()]

            query_template_step = utils.read_sql_file(os.path.join(sql_base_path, 'od_routing_step.sql'))
            routing_task = ui.progress.add_task("[bold magenta]Routing Demand", total=len(origins))
            ui.phases[6]["eta"] = f"~{int(len(origins)/10)}s" 
            for origin_id in origins:
                utils.execute_query(conn, query_template_step.format(network_table=network_table_name, location_prefix=f"{location_prefix}_{args.scenario_id}", origin_id=origin_id, edge_weight_column='cost', directed='false'))
                ui.progress.advance(routing_task)
                live.update(ui.get_dashboard_layout())

            utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, 'demand_finalize.sql')).format(network_table=network_table_name))
            ui.progress.remove_task(routing_task)

        # Stage 8: Aggregation
        ui.update_phase(8, "RUNNING")
        ui.progress.update(ui.overall_task, completed=88)
        agg_task = ui.progress.add_task("[bold green]H3 Aggregation", total=3)
        live.update(ui.get_dashboard_layout())
        
        queries = [
            ('osm_data_to_h3.sql', {'osm_table': osm_table_name, 'h3_table': h3_table_name}),
            ('ciclo_data_to_h3.sql', {'ciclo_table': ciclo_table_name, 'h3_table': h3_table_name}),
            ('components_data_to_h3.sql', {'component_table': base_components_table, 'h3_table': h3_table_name})
        ]
        for script, params in queries:
            utils.execute_query(conn, utils.read_sql_file(os.path.join(sql_base_path, script)).format(**params))
            ui.progress.advance(agg_task)
            live.update(ui.get_dashboard_layout())

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
    parser = argparse.ArgumentParser(description='Run necessary queries to create the tables with results in postgreSQL')
    parser.add_argument("--osm_input", dest="osm_input", required=False, type=str, help="osm network path")
    parser.add_argument("--ciclo_input", dest="ciclo_input", required=False, type=str, help="ciclos network path")
    parser.add_argument("--location", dest="location", required=True, type=str, help="location to process")
    parser.add_argument("--srid", dest="srid", required=False, type=str, help="SRID to use for calculate distance/metrics")
    parser.add_argument("--inhibit", dest="inhibit", required=True, type=int, help="inhibir o no la red")
    parser.add_argument("--inhibitor_input", dest="inhibitor_input", required=False, type=str, help="input of inibitor: None, 'osm' 'path/to/file'")
    parser.add_argument("--buffer_inhibidores", dest="buffer_inhib", required=False, type=int, help="metros de buffer aplicado a los inhibidores")
    parser.add_argument("--disinhit", dest="disinhit", required=True, type=int, help="desinhibir o no la red")
    parser.add_argument("--disinhitor_input", dest="disinhitor_input", required=False, type=str, help="input of dishinibitor: None, 'osm' 'path/to/file' ")
    parser.add_argument("--buffer_disinhibitor", dest="buffer_desinhib", required=False, type=int, help="metros de buffer aplicado a los desinhibidores")
    parser.add_argument("--proye", dest="proye", required=False, type=int, default=1, help="filter by parameter proye")
    parser.add_argument("--ci_o_cr", dest="ci_o_cr", required=False, type=int, default=1, help="filter by parameter ci_o_cr or 'bikepath or cross path'")
    parser.add_argument("--op_ci", dest="op_ci", required=False, type=int, default=1, help="filter by parameter op_ci operativity of the bikepath")
    
    # Phase 3 & 5: Scenario and demand parameters
    parser.add_argument("--scenario_id", dest="scenario_id", required=False, type=str, default="v1", help="unique identifier for this scenario (e.g. baseline, project_x)")
    parser.add_argument("--od_input", dest="od_input", required=False, type=str, help="path to the OD matrix CSV from Phase 1")
    parser.add_argument("--census_input", dest="census_input", required=False, type=str, help="path to the Census H3 enriched GeoJSON from Phase 1")

    args = parser.parse_args()

    # Define unified scenario-driven names
    location_prefix = utils.create_abbreviation(args.location)
    scenario_prefix = f"{location_prefix}_{args.scenario_id}"
    
    # Master tables (The ones the user sees in QGIS)
    network_table_name = f"{scenario_prefix}_network"
    h3_table_name = f"{scenario_prefix}_h3"
    
    # Intermediate / Internal names
    osm_table_name = f"{scenario_prefix}_osm_raw"
    ciclo_table_name = f"{scenario_prefix}_ciclos"
    inhibitor_table_name = f"{scenario_prefix}_inhibitor"
    desinhibitor_table_name = f"{scenario_prefix}_desinhibitor"

    data_pipeline(args.osm_input, args.ciclo_input, args.location, args.srid, args.inhibit, args.inhibitor_input, args.buffer_inhib, args.disinhit, args.disinhitor_input, args.buffer_desinhib, args.proye, args.ci_o_cr, args.op_ci, args.od_input, args.census_input, args, network_table_name, h3_table_name, osm_table_name, ciclo_table_name, inhibitor_table_name, desinhibitor_table_name)

if __name__=='__main__':
    main()
