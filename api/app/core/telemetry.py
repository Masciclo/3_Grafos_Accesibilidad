import os
import time
import socket
import hashlib
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from ui.components import diagnostic_handler

class TelemetryManager:
    def __init__(self, log_path="data/telemetry/telemetry_log.csv"):
        self.log_path = log_path
        self.models = {} # Dictionary of models per stage
        self.is_trained = False
        self.machine_hash = self._generate_machine_hash()
        self._ensure_log_exists()

    def _generate_machine_hash(self):
        try:
            return hashlib.md5((socket.gethostname() + str(os.cpu_count())).encode()).hexdigest()[:8]
        except:
            return "unknown"

    def _ensure_log_exists(self):
        columns = [
            'timestamp', 'machine_hash', 'osm_bytes', 'od_rows', 'has_projects', 'srid',
            't_total', 't_ingestion', 't_topo', 't_grid', 't_refactor', 't_routing', 't_agg', 't_final'
        ]
        if not os.path.exists(self.log_path):
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            df = pd.DataFrame(columns=columns)
            df.to_csv(self.log_path, index=False)
        else:
            # Migration: Ensure new columns exist
            try:
                df = pd.read_csv(self.log_path, nrows=1)
                missing = [c for c in columns if c not in df.columns]
                if missing:
                    full_df = pd.read_csv(self.log_path)
                    for c in missing:
                        full_df[c] = np.nan
                    full_df.to_csv(self.log_path, index=False)
            except:
                pass

    def log_run(self, osm_path, od_path, has_projects, srid, timings):
        """
        Records the dimensions and per-stage timings of a completed run.
        timings: dict with keys like 't_ingestion', 't_routing', etc.
        """
        try:
            osm_bytes = os.path.getsize(osm_path) if osm_path and os.path.exists(osm_path) else 0
            od_rows = 0
            if od_path and os.path.exists(od_path):
                with open(od_path, 'rb') as f:
                    od_rows = sum(1 for _ in f) - 1

            new_data = {
                'timestamp': time.time(),
                'machine_hash': self.machine_hash,
                'osm_bytes': osm_bytes,
                'od_rows': od_rows,
                'has_projects': 1 if has_projects else 0,
                'srid': srid,
                't_total': timings.get('t_total', 0)
            }
            # Map specific stages
            for stage in ['ingestion', 'topo', 'grid', 'refactor', 'routing', 'agg', 'final']:
                new_data[f't_{stage}'] = timings.get(f't_{stage}', 0)
            
            df = pd.DataFrame([new_data])
            df.to_csv(self.log_path, mode='a', header=False, index=False)
            diagnostic_handler.report("TELEMETRY_LOGGED", "INFO", f"Run recorded for machine {self.machine_hash}")
        except Exception as e:
            diagnostic_handler.report("TELEMETRY_ERROR", "WARNING", f"Failed to log telemetry: {e}")

    def train_model(self):
        """
        Trains Log-Log models for each stage based on historical data from the SAME machine.
        """
        try:
            df = pd.read_csv(self.log_path)
            # Filter by machine hash to ensure calibration
            df = df[df['machine_hash'] == self.machine_hash].dropna(subset=['osm_bytes', 'od_rows', 't_total'])
            
            if len(df) < 3:
                return False
            
            # Log-Log Transformation: log(time) = b0 + b1*log(osm) + b2*log(od)
            # We add 1 to avoid log(0)
            X = np.log1p(df[['osm_bytes', 'od_rows', 'has_projects']].values)
            
            stages = ['total', 'ingestion', 'topo', 'grid', 'refactor', 'routing', 'agg', 'final']
            for stage in stages:
                target = f't_{stage}'
                if target in df.columns and df[target].sum() > 0:
                    y = np.log1p(df[target].values)
                    model = LinearRegression()
                    model.fit(X, y)
                    self.models[stage] = model
            
            self.is_trained = True
            diagnostic_handler.report("MODEL_TRAINED", "INFO", f"Log-Log models calibrated for machine {self.machine_hash} ({len(df)} runs).")
            return True
        except Exception as e:
            diagnostic_handler.report("MODEL_ERROR", "WARNING", f"Model training failed: {e}")
            return False

    def _get_scale_defaults(self, osm_input_path, od_input_path):
        """Calculates scale-aware baseline defaults based on OD matrix rows and location hints."""
        od_rows = 0
        if od_input_path and os.path.exists(od_input_path):
            try:
                with open(od_input_path, 'rb') as f:
                    od_rows = sum(1 for _ in f) - 1
            except Exception:
                pass

        str_hint = str(osm_input_path).lower() + " " + str(od_input_path).lower()
        is_metro = od_rows > 1000000 or 'santiago' in str_hint or 'sant' in str_hint
        is_medium = od_rows > 100000 or 'valparaiso' in str_hint or 'concepcion' in str_hint

        if is_metro:
            return {'total': 21600, 'ingestion': 300, 'topo': 450, 'grid': 480, 'refactor': 900, 'routing': 19200, 'agg': 180, 'final': 2400}
        elif is_medium:
            return {'total': 3600, 'ingestion': 60, 'topo': 90, 'grid': 60, 'refactor': 300, 'routing': 2700, 'agg': 120, 'final': 300}
        else:
            return {'total': 300, 'ingestion': 10, 'topo': 15, 'grid': 10, 'refactor': 40, 'routing': 180, 'agg': 30, 'final': 60}

    def predict_eta(self, osm_input_path, od_input_path, has_projects, stage='total'):
        """
        Predicts duration for a specific stage or the total pipeline.
        """
        defaults = self._get_scale_defaults(osm_input_path, od_input_path)
        
        if not self.is_trained:
            self.train_model()
            
        if not self.is_trained or stage not in self.models:
            return defaults.get(stage, 60)

        try:
            osm_bytes = os.path.getsize(osm_input_path) if osm_input_path and os.path.exists(osm_input_path) else 0
            od_rows = 0
            if od_input_path and os.path.exists(od_input_path):
                with open(od_input_path, 'rb') as f:
                    od_rows = sum(1 for _ in f) - 1
            
            X_new = np.log1p(np.array([[osm_bytes, od_rows, 1 if has_projects else 0]]))
            log_prediction = self.models[stage].predict(X_new)[0]
            prediction = np.expm1(log_prediction)
            
            return max(prediction, 5) # Minimum 5 seconds
        except:
            return defaults.get(stage, 60)

    def format_eta(self, seconds):
        if seconds < 60:
            return f"~{int(seconds)}s"
        elif seconds < 3600:
            return f"~{int(seconds // 60)}m"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"~{hours}h {mins}m"

# Static instance
telemetry_manager = TelemetryManager()


class NetworkOntologyProfiler:
    """
    Queries PostGIS spatial network and demand tables before interactive grilling.
    Extracts top BFS cycleway components, H3 demand hotspots, and network statistics.
    """

    def __init__(self, db_config: dict, net_prefix: str, reference_scenario: str = "current"):
        self.db_config = db_config
        self.net_prefix = net_prefix
        self.reference_scenario = reference_scenario
        self.net_table = f"{net_prefix}_{reference_scenario}_internal_net"

    def _get_conn(self):
        from infra.database import create_conn
        return create_conn(
            self.db_config['name'],
            self.db_config['host'],
            self.db_config['port'],
            self.db_config['user'],
            self.db_config['password']
        )

    def profile_city(self) -> dict:
        conn = self._get_conn()
        cur = conn.cursor()
        
        top_components = []
        demand_hotspots = []
        summary = {"total_edges": 0, "cycleway_edges": 0, "total_cycleway_length_m": 0.0}

        try:
            # 1. Network Summary
            cur.execute(f"""
                SELECT 
                    COUNT(*), 
                    COUNT(*) FILTER (WHERE highway = 'cycleway'),
                    COALESCE(SUM(ST_Length(geometry)) FILTER (WHERE highway = 'cycleway'), 0.0)
                FROM {self.net_table};
            """)
            row = cur.fetchone()
            if row:
                summary["total_edges"] = row[0]
                summary["cycleway_edges"] = row[1]
                summary["total_cycleway_length_m"] = float(row[2])

            # 2. Top BFS Cycleway Components by Flow and Length
            try:
                cur.execute(f"""
                    SELECT 
                        COALESCE(CAST(component_id AS TEXT), 'c_main') as comp_id,
                        COUNT(*) as edges,
                        SUM(COALESCE(od_flow, 0)) as total_flow,
                        SUM(ST_Length(geometry)) as total_len
                    FROM {self.net_table}
                    WHERE highway = 'cycleway'
                    GROUP BY comp_id
                    ORDER BY total_flow DESC
                    LIMIT 5;
                """)
                top_components = cur.fetchall()
            except Exception:
                conn.rollback()
                top_components = []

            # 3. Top H3 Demand Hotspots
            h3_table = f"{self.net_prefix}_h3"
            try:
                cur.execute(f"""
                    SELECT h3_index, SUM(trips) as total_trips
                    FROM {h3_table}
                    GROUP BY h3_index
                    ORDER BY total_trips DESC
                    LIMIT 10;
                """)
                demand_hotspots = cur.fetchall()
            except Exception:
                conn.rollback()
                demand_hotspots = []

        except Exception as e:
            diagnostic_handler.report("PROFILER_ERROR", "WARNING", f"Could not profile network ontology: {e}")
        finally:
            cur.close()
            conn.close()

        return {
            "net_prefix": self.net_prefix,
            "reference_scenario": self.reference_scenario,
            "summary": summary,
            "top_components": top_components
        }

