import json
import os
import psutil
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

class BannerAnimator:
    def __init__(self, json_path):
        self.frames = []
        self.current_frame = 0
        self.fps = 30
        self.load_frames(json_path)

    def load_frames(self, path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                self.fps = data.get('animation', {}).get('frameRate', 30)
                for f in data.get('frames', []):
                    self.frames.append("\n".join(f.get('content', [])))
        except Exception as e:
            console.print(f"[red]Error loading banner:[/] {e}")
            self.frames = ["+ C I C L O +"]

    def get_next_frame(self):
        if not self.frames: return ""
        frame = self.frames[self.current_frame]
        self.current_frame = (self.current_frame + 1) % len(self.frames)
        return frame

class DiagnosticHandler:
    '''
    Description: Handles Phase 4 Observability Framework (Errors and Warnings).
    '''
    def __init__(self):
        self.diagnostics = []

    def report(self, code, level, message):
        emoji = "💡" if level == "INFO" else "⚠️" if level == "WARNING" else "🔴"
        color = "cyan" if level == "INFO" else "yellow" if level == "WARNING" else "red"
        self.diagnostics.append({"code": code, "level": level, "message": message, "color": color, "emoji": emoji})
        console.print(f"{emoji} [{color} BOLD][{level}] {code}:[/] {message}")

    def check_environment(self, conn):
        '''Technical: Check database capabilities and connection'''
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT postgis_version();")
                pg_ver = cursor.fetchone()[0]
                self.report("POSTGIS_CHECK", "INFO", f"PostGIS Active: {pg_ver}")
                
                cursor.execute("SELECT count(*) FROM pg_extension WHERE extname = 'pgrouting';")
                pgr_active = cursor.fetchone()[0] > 0
                if not pgr_active:
                    self.report("PGROUTING_MISSING", "ERROR", "pgRouting extension not found in database.")
                    return False
                self.report("PGROUTING_CHECK", "INFO", "pgRouting extension verified.")
            return True
        except Exception as e:
            self.report("ENV_CHECK_FAILED", "ERROR", f"Environment audit failed: {str(e)}")
            return False

    def validate_inputs(self, od_path, census_path, projects_path=None):
        results = []
        if od_path:
            exists = os.path.exists(od_path)
            status = "[green]EXISTS[/]" if exists else "[red]MISSING[/]"
            results.append(["OD Matrix", os.path.basename(od_path), status])
            if exists and od_path.endswith('.csv'):
                try:
                    df_test = pd.read_csv(od_path, nrows=5)
                    required = ['h3_origin', 'h3_dest', 'trips']
                    missing = [col for col in required if col not in df_test.columns]
                    if missing:
                        self.report("INVALID_FORMAT", "ERROR", f"OD Matrix missing: {missing}")
                    else:
                        results.append(["OD Schema", "Columns Validated", "[green]PASSED[/]"])
                except:
                    results.append(["OD Schema", "Read Error", "[red]FAILED[/]"])
        
        if census_path:
            exists = os.path.exists(census_path)
            status = "[green]EXISTS[/]" if exists else "[red]MISSING[/]"
            results.append(["Census Data", os.path.basename(census_path), status])

        if projects_path:
            exists = os.path.exists(projects_path)
            status = "[green]EXISTS[/]" if exists else "[red]MISSING[/]"
            results.append(["Scenario Projects", os.path.basename(projects_path), status])
        return results

    def get_input_table(self, od_path, census_path, projects_path=None):
        table = Table(title="[bold blue]Pre-flight Input Checklist", box=None, expand=True)
        table.add_column("Resource", style="bold")
        table.add_column("Source/Detail")
        table.add_column("Status", justify="right")
        
        results = self.validate_inputs(od_path, census_path, projects_path)
        for res in results:
            table.add_row(*res)
        return table

    def get_mem_usage(self):
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # In MB

    def audit_network(self, conn, table_name, components_table):
        query = f"SELECT count(*) as total, count(*) FILTER (WHERE component != (SELECT component FROM {components_table} GROUP BY component ORDER BY count(*) DESC LIMIT 1)) as isolated FROM {components_table};"
        with conn.cursor() as cursor:
            cursor.execute(query)
            res = cursor.fetchone()
            isolated_pct = (res[1] / res[0]) * 100 if res[0] > 0 else 0
            if isolated_pct > 20:
                self.report("NETWORK_FRAGMENTATION", "WARNING", f"Graph is highly fragmented. {isolated_pct:.1f}% of nodes are isolated islands.")
            else:
                self.report("TOPOLOGY_HEALTH", "INFO", f"Network connected. Isolated nodes: {isolated_pct:.1f}%")

# Static instance for global pipeline visibility
diagnostic_handler = DiagnosticHandler()
