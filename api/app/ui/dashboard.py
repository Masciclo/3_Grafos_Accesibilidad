import time
import sys
import os
from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from ui.components import BannerAnimator, diagnostic_handler

console = Console(force_terminal=True, color_system="truecolor")

class PipelineUI:
    def __init__(self, location, srid, args=None):
        self.location = location
        self.srid = srid
        self.args = args
        self.banner_path = os.path.join(os.path.dirname(__file__), "assets", "banner.json")
        self.animator = BannerAnimator(self.banner_path)
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
                if status == "RUNNING": 
                    p["start"] = now
                if "DONE" in status:
                    p["end"] = now
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
            Layout(Panel(diagnostic_handler.get_input_table(self.args.od_input if self.args else None, self.args.census_input if self.args else None, self.args.projects_input if self.args else None), border_style="blue"))
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
        for d in diagnostic_handler.diagnostics[-5:]:
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
