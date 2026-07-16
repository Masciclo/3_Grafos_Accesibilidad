import json
import os
import psutil
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

def hex_to_ansi256(hex_str):
    h = hex_str.lstrip('#').lower()
    # Explicit mapping for +Ciclo palette to ensure exact representation
    mapping = {
        "ffffff": 15,    # White
        "ffbe0b": 214,   # Yellow
        "fb5607": 202,   # Orange
        "ff006e": 197,   # Pink
        "8338ec": 99     # Purple
    }
    if h in mapping:
        return mapping[h]
        
    try:
        r, g, b = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        if r == g == b:
            if r < 8: return 16
            if r > 248: return 15
            return round(((r - 8) / 247) * 24) + 232
        def to_cube(val):
            if val < 48: return 0
            if val < 115: return 1
            if val < 155: return 2
            if val < 195: return 3
            if val < 235: return 4
            return 5
        return 16 + 36 * to_cube(r) + 6 * to_cube(g) + to_cube(b)
    except:
        return 7  # Fallback to default white/grey

class BannerAnimator:
    def __init__(self, json_path):
        self.frames = []
        self.raw_frames = []
        self.current_frame = 0
        self.fps = 12
        self.width = 80
        self.height = 24
        self.load_frames(json_path)

    def load_frames(self, path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                self.fps = data.get('animation', {}).get('frameRate', 12)
                
                canvas = data.get('canvas', {})
                self.width = canvas.get('width', 80)
                self.height = canvas.get('height', 24)

                for f_data in data.get('frames', []):
                    content = f_data.get('content', [])
                    colors_raw = f_data.get('colors', {}).get('foreground', "{}")
                    try:
                        color_map = json.loads(colors_raw)
                    except:
                        color_map = {}
                    
                    frame_ansi = ""
                    for y in range(self.height):
                        line = content[y] if y < len(content) else ""
                        row_ansi = ""
                        last_color = None
                        
                        # Process only up to the last visible character to prevent trailing artifacts
                        max_x = len(line)
                        for coord in color_map.keys():
                            try:
                                cx, cy = map(int, coord.split(','))
                                if cy == y: max_x = max(max_x, cx + 1)
                            except: continue

                        for x in range(max_x):
                            char = line[x] if x < len(line) else " "
                            color = color_map.get(f"{x},{y}")
                            
                            if color != last_color:
                                if color:
                                    idx = hex_to_ansi256(color)
                                    row_ansi += f"\033[38;5;{idx}m"
                                else:
                                    row_ansi += "\033[39m"
                                last_color = color
                            row_ansi += char
                        
                        frame_ansi += row_ansi + "\033[0m\n"
                    
                    self.raw_frames.append(frame_ansi)
                    self.frames.append(Text.from_ansi(frame_ansi))
                    
        except Exception as e:
            msg = "+ C I C L O +"
            self.frames = [Text(msg, style="bold green")]
            self.raw_frames = [f"\033[32;1m{msg}\033[0m\n"]

    def play_intro(self, loops=1):
        import sys, time, select, shutil
        
        # Check window size limits first
        tw, th = shutil.get_terminal_size()
        if tw < self.width or th < self.height:
            sys.stdout.write("\033[2J\033[H\033[32;1m+ C I C L O +\033[0m\n")
            sys.stdout.flush()
            time.sleep(0.8)
            return

        # Hide cursor and clear screen
        sys.stdout.write("\033[2J\033[H\033[?25l")
        
        # Clear stdin buffer if it's a TTY to prevent immediate skip from leftover input
        if sys.stdin.isatty():
            try:
                while select.select([sys.stdin], [], [], 0.0)[0]:
                    sys.stdin.read(1)
            except Exception:
                pass

        try:
            for _ in range(loops):
                for frame in self.raw_frames:
                    # Skip check (only if standard interactive TTY)
                    if sys.stdin.isatty():
                        try:
                            if select.select([sys.stdin], [], [], 0.0)[0]:
                                sys.stdin.read(1)  # Consume the keypress character
                                return
                        except Exception:
                            pass
                    
                    tw, th = shutil.get_terminal_size()
                    px, py = max(0, (tw-self.width)//2), max(0, (th-self.height)//2)
                    
                    # Optimized rendering: Jump to top and pad
                    sys.stdout.write("\033[H" + ("\n"*py))
                    for line in frame.split('\n'):
                        sys.stdout.write((" "*px) + line + "\n")
                    sys.stdout.flush()
                    time.sleep(1/self.fps)
            
            # Post-animation hold on the final frame (0.8s) to allow visual absorption
            time.sleep(0.8)
            
        finally:
            # Restore cursor and clear screen
            sys.stdout.write("\033[?25h\033[0m\033[2J\033[H")
            sys.stdout.flush()

    def get_ansi_frame(self):
        if not self.frames: return Text("")
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
                except Exception as e:
                    self.report("READ_ERROR", "ERROR", f"Could not read OD Matrix: {e}")
        
        if census_path:
            exists = os.path.exists(census_path)
            status = "[green]EXISTS[/]" if exists else "[red]MISSING[/]"
            results.append(["Census Data", os.path.basename(census_path), status])

        if projects_path:
            exists = os.path.exists(projects_path)
            status = "[green]EXISTS[/]" if exists else "[red]MISSING[/]"
            results.append(["Project Data", os.path.basename(projects_path), status])
            
        return results

    def get_mem_usage(self):
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)

diagnostic_handler = DiagnosticHandler()
