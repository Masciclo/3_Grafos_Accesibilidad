import os
import sys
import time
import shutil
import queue
import threading
from typing import Optional

class ExecutionLogger:
    """
    Asynchronous Thread-Safe Logger for +Ciclo Pipeline.
    Streams granular evaluation logs to phase-specific disk files under data/{city}/logs/{scenario_id}/
    while mirroring CRITICAL, ERROR, and STOP alerts directly to the console.
    """

    def __init__(self, data_base_path: str, city_key: str, scenario_id: str):
        self.data_base_path = data_base_path
        self.city_key = city_key
        self.scenario_id = scenario_id
        self.log_dir = os.path.join(data_base_path, city_key, "logs", scenario_id)
        os.makedirs(self.log_dir, exist_ok=True)

        self.log_queue = queue.Queue()
        self.active_phase = "01_recommendation"
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._worker_thread.start()

    def set_phase(self, phase_name: str):
        """Sets the active phase file for incoming log streams."""
        self.active_phase = phase_name

    def log(self, message: str, level: str = "INFO", console_alert: bool = False):
        """Enqueues a log entry. Mirrors to console if level is CRITICAL/ERROR/STOP or console_alert is True."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level.upper()}] {message}\n"
        self.log_queue.put((self.active_phase, entry))

        if console_alert or level.upper() in ("CRITICAL", "ERROR", "STOP"):
            try:
                from rich.console import Console
                Console().print(f"[bold red][{level.upper()}][/] {message}")
            except Exception:
                print(f"[{level.upper()}] {message}", file=sys.stderr)

    def _writer_loop(self):
        """Worker thread loop flushing queued log records to disk."""
        while not self._stop_event.is_set() or not self.log_queue.empty():
            try:
                phase, entry = self.log_queue.get(timeout=0.2)
                file_path = os.path.join(self.log_dir, f"{phase}.log")
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(entry)
                self.log_queue.task_done()
            except queue.Empty:
                continue

    def close(self):
        """Flushes remaining queue entries and safely terminates worker thread."""
        self._stop_event.set()
        self._worker_thread.join(timeout=2.0)


class ExecutionCacheManager:
    """
    Manages city-level execution log archives and auto-purging policies.
    Identifies uncommitted temporary run folders and purges them before new runs,
    while preserving explicitly named scenario archives permanently.
    """

    @staticmethod
    def purge_temporary_logs(data_base_path: str, city_key: str, keep_scenarios: Optional[list] = None):
        """Purges uncommitted temporary log folders for a given city."""
        logs_root = os.path.join(data_base_path, city_key, "logs")
        if not os.path.exists(logs_root):
            return

        protected = set(keep_scenarios or ["baseline", "current", "v0_baseline", "v1_current"])
        
        for item in os.listdir(logs_root):
            item_path = os.path.join(logs_root, item)
            if os.path.isdir(item_path):
                # Protect named scenarios or explicitly protected IDs
                if item in protected or item.startswith("rec_") or item.startswith("scen_"):
                    continue
                # Purge uncommitted temp logs
                try:
                    shutil.rmtree(item_path)
                except Exception as e:
                    print(f"[Warning] Could not purge temp log dir {item_path}: {e}")

    @staticmethod
    def register_scenario_archive(data_base_path: str, city_key: str, scenario_id: str):
        """Ensures a scenario log directory exists and is marked for permanent retention."""
        scenario_log_dir = os.path.join(data_base_path, city_key, "logs", scenario_id)
        os.makedirs(scenario_log_dir, exist_ok=True)
