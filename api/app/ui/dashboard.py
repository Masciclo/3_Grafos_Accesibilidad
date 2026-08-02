import time
import sys
import os
from typing import Optional, Dict
from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from ui.components import BannerAnimator, diagnostic_handler
from core.telemetry import telemetry_manager

console = Console(force_terminal=True, color_system="truecolor")

class PipelineUI:
    def __init__(self, location, srid, args=None):
        self.location = location
        self.srid = srid
        self.args = args
        self.banner_path = os.path.join(os.path.dirname(__file__), "assets", "masciclo2.1.json")
        self.animator = BannerAnimator(self.banner_path)
        self.completed = False
        
        # --- Task 13.9: Conditional Phase Registration ---
        is_comparison = bool(getattr(args, "reference_scenario", None) or getattr(args, "projects_input", None))
        
        all_phases = [
            {"id": 1, "name": "Data Ingestion", "steps": 4},
            {"id": 2, "name": "Topology Creation", "steps": 2},
            {"id": 3, "name": "Grid Extraction", "steps": 100}, # Percentage-based
            {"id": 4, "name": "H3 Snapping", "steps": 1, "optional": True},
            {"id": 5, "name": "Topology Refactoring", "steps": 6},
            {"id": 6, "name": "Intermodal Merging", "steps": 1, "optional": True},
            {"id": 7, "name": "Demand Routing", "steps": 100}, # Origins-based
            {"id": 8, "name": "H3 Aggregation", "steps": 6},
            {"id": 9, "name": "Analytical Closing & Audit", "steps": 2}
        ]
        
        self.phases = [p for p in all_phases if not p.get("optional") or is_comparison]
        
        # Unified Progress System
        self.progress = Progress(
            SpinnerColumn(spinner_name="dots", style="bold cyan"),
            TextColumn("[progress.description]{task.description}", justify="left"),
            BarColumn(bar_width=20, pulse_style="cyan"),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn()
        )
        
        # Initialize Task IDs for each phase
        for p in self.phases:
            p["task_id"] = self.progress.add_task("", total=p["steps"], visible=False)
            p["status"] = "PENDING"
            p["start"] = None
            p["end"] = None
            p["eta"] = "Auto"
 
        self.overall_task = self.progress.add_task("[bold white]Overall Simulation", total=len(self.phases))

    def update_phase(self, phase_id, status="RUNNING", increment=0, total=None):
        now = time.time()
        for p in self.phases:
            if p["id"] == phase_id:
                p["status"] = status
                task = self.progress._tasks[p["task_id"]]
                
                if status == "RUNNING":
                    if not p["start"]: p["start"] = now
                    self.progress.update(p["task_id"], visible=True)
                
                if increment > 0:
                    self.progress.advance(p["task_id"], advance=increment)
                
                if total:
                    self.progress.update(p["task_id"], total=total)

                if "DONE" in status:
                    p["end"] = now
                    self.progress.update(p["task_id"], completed=task.total)
                    self.progress.update(self.overall_task, advance=1)

    def format_time(self, seconds):
        if seconds is None: return "--"
        if seconds < 60:
            return f"{int(seconds)}s"
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"

    def make_config_table(self):
        table = Table(title="[bold white]Pipeline Configuration", border_style="white", box=None)
        table.add_column("Parameter", style="bold white")
        table.add_column("Value", style="white")
        if self.args:
            table.add_row("Location", self.location)
            table.add_row("Scenario", getattr(self.args, "scenario_id", "v1"))
            table.add_row("SRID", str(self.srid))
            
            # Use getattr for optional/new flags to prevent crashes
            inhibit_status = "Enabled" if getattr(self.args, "inhibit", True) else "Disabled"
            table.add_row("Inhibition", inhibit_status)
        return table

    def get_landing_layout(self, prompt_text=None):
        from rich.align import Align
        layout = Layout()
        layout.split_column(
            Layout(name="banner", ratio=1),
            Layout(name="prompt", size=3)
        )
        # Use ANSI-backed frame for color stability
        frame = self.animator.get_ansi_frame()
        
        layout["banner"].update(
            Align.center(frame, vertical="middle")
        )
        
        display_text = prompt_text if prompt_text else "[bold green]waiting for query...[/]"
        layout["prompt"].update(Panel(display_text, border_style="white", padding=(0, 2)))
        return layout

    def get_audit_layout(self, census_map, od_map, spatial_status="VALID"):
        # Meta Table
        meta_table = Table(box=None, expand=True)
        meta_table.add_column("Dataset", style="bold white")
        meta_table.add_column("Attribute", style="white")
        meta_table.add_column("Mapped Column", style="white")
        for k, v in census_map.items(): meta_table.add_row("Census", k, v)
        for k, v in od_map.items(): meta_table.add_row("Demand", k, v)
        
        # Phase Budget Table
        budget_table = Table(box=None, expand=True)
        budget_table.add_column("#", style="dim")
        budget_table.add_column("Planned Stage", style="bold white")
        budget_table.add_column("Predicted ETA", style="dim")
        for p in self.phases:
            budget_table.add_row(str(p["id"]), p["name"], p["eta"])

        guard_style = "green" if spatial_status == "VALID" else "red"
        guard_msg = "[bold green]✓ SPATIAL ANCHORING VALIDATED:[/] Data extent matches requested BBOX." if spatial_status == "VALID" else "[bold red]⚠ SPATIAL ANCHORING GUARD:[/] Data extent MISMATCH detected. Ghost simulation risk."
        
        from rich.align import Align
        controls = "[bold green][C] Launch Analysis[/] | [bold yellow][R] Redefine Parameters[/] | [bold red][Ctrl+C] Abort[/]"
        
        return Group(
            Panel(f"[bold white]SCREEN 2: Pre-flight Audit Monitoring[/] [dim]Area: {self.location} | Scenario: {getattr(self.args, 'scenario_id', 'v1')}[/]", border_style="white"),
            Group(
                Panel(meta_table, title="[bold white]Metadata Standardization", border_style="white"),
                Panel(budget_table, title="[bold white]Estimated Phase Budget", border_style="white")
            ),
            Panel(guard_msg, title="[bold white]Safety Guard", border_style=guard_style),
            Panel(Align.center(controls), border_style="dim")
        )

    def get_dashboard_layout(self):
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=1),
            Layout(name="body", ratio=1),
            Layout(name="telemetry", size=4),
            Layout(name="diagnostics", size=5),
            Layout(name="footer", size=1)
        )
        # Compact Header
        header_text = Text.from_markup(f" [bold black on white] +CICLO [/] [bold white] Mission Control: {self.location} [/] [dim]|[/] [white] Scenario: {self.args.scenario_id} [/]")
        layout["header"].update(header_text)
        
        # --- Body: Unified Engineering Panel ---
        # 1. Overall Header
        overall_table = self.progress.make_tasks_table([self.progress._tasks[self.overall_task]])
        
        # 2. Granular Status Table with Inline Progress
        status_table = Table(box=None, expand=True, padding=(0, 1))
        status_table.add_column("#", style="dim", width=2)
        status_table.add_column("Operational Stage", style="bold white", width=25)
        status_table.add_column("Progress", width=30)
        status_table.add_column("Status", justify="center")
        status_table.add_column("Elapsed", justify="right", style="dim")
        status_table.add_column("ETA", style="dim")

        # Ensure all phases are marked DONE if pipeline completed
        if self.completed:
            for p in self.phases:
                p["status"] = "DONE ✅"
                task = self.progress._tasks[p["task_id"]]
                self.progress.update(p["task_id"], completed=task.total)
            self.progress.update(self.overall_task, completed=len(self.phases))

        for p in self.phases:
            # DYNAMIC TIMER LOGIC
            elapsed_val = None
            if p["status"] == "RUNNING" and p["start"]:
                elapsed_val = time.time() - p["start"]
            elif "DONE" in p["status"] and p["start"] and p["end"]:
                elapsed_val = p["end"] - p["start"]
            
            elapsed_str = self.format_time(elapsed_val) if elapsed_val else "--"
            status_style = "bold green" if "DONE" in p["status"] else "bold cyan" if "RUNNING" in p["status"] else "dim"
            
            # Inline Progress Bar
            task = self.progress._tasks[p["task_id"]]
            inline_bar = self.progress.make_tasks_table([task]) if p["status"] != "PENDING" else "[dim]........[/]"

            status_table.add_row(
                str(p["id"]),
                p["name"],
                inline_bar,
                f"[{status_style}]{p['status']}[/]",
                elapsed_str,
                p["eta"]
            )

        layout["body"].update(Panel(
            Group(
                Panel(overall_table, border_style="white", title="[bold white]Overall Mission Status"),
                status_table
            ), 
            title="[bold white]Analytical Pipeline", 
            border_style="white"
        ))

        # Telemetry-Rich Metrics
        metrics = Table.grid(expand=True, padding=(0, 2))
        mem = diagnostic_handler.get_mem_usage()
        metrics.add_row(
            f" [dim]RAM:[/] [bold]{mem:.1f} MB[/]", 
            f" [dim]DB:[/] [green]Active[/]",
            f" [dim]Machine:[/] [bold]{getattr(self.args, 'machine_hash', 'unknown')[:8]}[/]", 
            f" [dim]Model:[/] [bold]Log-Log[/]"
        )
        layout["telemetry"].update(Panel(metrics, title="[bold white]System Metrics", border_style="white"))

        diag_list = []
        for d in diagnostic_handler.diagnostics[-3:]:
            diag_list.append(Text.from_markup(f" {d['emoji']} [dim]{d['level']}:[/] {d['message']}"))
        if not diag_list: diag_list = [Text(" Monitoring live telemetry...", style="dim")]
        layout["diagnostics"].update(Panel(Group(*diag_list), title="[bold dim]Diagnostic Feed", border_style="white"))
        
        footer_msg = Text.from_markup(f" [bold green]✓ Pipeline Completed Successfully! 🎉[/]" if self.completed else " [italic dim]Processing architectural hooks...[/]")
        layout["footer"].update(footer_msg)
        return layout

from core.pipeline import ProgressSeam

class RichProgressAdapter(ProgressSeam):
    """
    RichProgressAdapter: Bridges ScenarioEngine events to the Rich Dashboard.
    """
    def __init__(self, ui: PipelineUI):
        self.ui = ui
        self.routing_task_id = None
        self.agg_task_id = None
        self.refactor_task_id = None

    def on_stage_start(self, stage_id: int, name: str, eta: str = "Auto"):
        # Resolve ETA if still 'Auto' using telemetry manager
        if eta == "Auto":
            stage_map = {1: 'ingestion', 2: 'topo', 3: 'grid', 5: 'refactor', 7: 'routing', 8: 'agg', 9: 'final'}
            key = stage_map.get(stage_id)
            if key and self.ui.args:
                raw_pred = telemetry_manager.predict_eta(
                    getattr(self.ui.args, 'osm_input', 'osm'), 
                    getattr(self.ui.args, 'od_input', 'od'), 
                    bool(getattr(self.ui.args, 'projects_input', None)), 
                    stage=key
                )
                eta = telemetry_manager.format_eta(raw_pred)

        # Safe lookup for pruned phases
        target = next((p for p in self.ui.phases if p["id"] == stage_id), None)
        if target:
            target["eta"] = eta
        self.ui.update_phase(stage_id, "RUNNING")

    def on_stage_end(self, stage_id: int, success: bool = True):
        status = "DONE ✅" if success else "FAILED ❌"
        self.ui.update_phase(stage_id, status)

    def on_progress_update(self, *args, **kwargs):
        # Handle variable positional arguments from different modules
        # Some modules pass (pid, status), some just (status)
        status = args[0] if len(args) == 1 else args[1] if len(args) > 1 else None
        increment = kwargs.get('increment', 0)
        total = kwargs.get('total')

        # Map generic signals to Phase IDs
        signal_to_id = {
            "ADVANCE_ROUTING": 7,
            "ADVANCE_REFACTOR": 5,
            "ADVANCE_AGGREGATION": 8,
            "ADVANCE_MAPPING": 9
        }
        
        phase_id = signal_to_id.get(status)
        if phase_id:
            self.ui.update_phase(phase_id, "RUNNING", increment=increment, total=total)
        elif status == "ADVANCE_GRID": # Task 13.9: H3 Grid specific
            self.ui.update_phase(3, "RUNNING", increment=increment, total=total)

    def report_diagnostic(self, tag: str, level: str, message: str):
        diagnostic_handler.report(tag, level, message)

    def get_timings(self) -> Dict[str, float]:
        """
        Extracts duration for each stage from the UI phase tracking.
        """
        timings = {}
        stage_map = {
            1: 'ingestion', 2: 'topo', 3: 'grid', 
            5: 'refactor', 7: 'routing', 8: 'agg', 9: 'final'
        }
        for p in self.ui.phases:
            key = stage_map.get(p["id"])
            if key and p["start"] and p["end"]:
                timings[f"t_{key}"] = p["end"] - p["start"]
        return timings
