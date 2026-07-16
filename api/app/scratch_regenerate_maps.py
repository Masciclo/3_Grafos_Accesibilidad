import os
import sys
import psycopg2
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List

# Load project path
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Monkeypatch create_abbreviation before importing RoutingVisualizer
import infra.ingestion
infra.ingestion.create_abbreviation = lambda x: "valdchil" if x == "valdchil" else ("santchil" if x == "santiago" else "vald")

from core.pipeline import ScenarioConfig, ScenarioContext, ProgressSeam
from core.routing_visualizer import RoutingVisualizer

load_dotenv()

class ConsoleProgressSeam(ProgressSeam):
    def on_stage_start(self, stage_id: int, name: str, eta: str = "Auto"):
        print(f"Starting stage {stage_id}: {name}")
    def on_stage_end(self, stage_id: int, success: bool = True):
        print(f"Ended stage {stage_id}: success={success}")
    def on_progress_update(self, *args, **kwargs):
        print(f"Progress update: args={args} kwargs={kwargs}")
    def report_diagnostic(self, tag: str, level: str, message: str):
        print(f"[{level}] {tag}: {message}")
    def get_timings(self):
        return {}

def run_regeneration():
    db_config = {
        'name': os.getenv('DATABASE_NAME'),
        'host': os.getenv('HOST'),
        'port': os.getenv('PORT'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD')
    }
    conn = psycopg2.connect(
        dbname=db_config['name'],
        host=db_config['host'],
        port=db_config['port'],
        user=db_config['user'],
        password=db_config['password']
    )
    
    cur = conn.cursor()
    cur.execute("SELECT SUM(trips) FROM valdchil_project_v1_od_matrix;")
    total_trips = float(cur.fetchone()[0] or 1.0)
    print("Total trips in DB (Valdivia):", total_trips)
    
    config = ScenarioConfig(
        location="valdchil",
        city_key="valdchil",
        scenario_id="project_v1",
        srid=32719,
        osm_input="osm",
        od_input="data/valdivia/in/od_matrix_micro.csv",
        census_input="data/shared/census/chl/census_2024_pais.parquet",
        projects_input="data/valdivia/in/projects.geojson",
        reference_scenario="baseline",
        bbox=None,
        mapping=True
    )
    
    context = ScenarioContext(
        config=config,
        conn=conn,
        observer=ConsoleProgressSeam(),
        db_config=db_config,
        tables={
            'net': "valdchil_project_v1_internal_net",
            'h3': "valdchil_project_v1_internal_h3",
            'osm': "valdchil_project_v1_osm_raw",
            'ciclo': "valdchil_project_v1_ciclos",
            'projects': "valdchil_project_v1_projects",
            'census': "valdchil_project_v1_census",
            'zones': "valdchil_project_v1_zones"
        },
        state={
            'total_trips': total_trips,
            'sql_base_path': os.path.join(os.path.dirname(os.path.realpath(__file__)), 'sql', 'common'),
            'data_base_path': os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data')
        }
    )
    
    visualizer = RoutingVisualizer(context)
    visualizer.execute()
    print("Valdivia Maps regenerated successfully!")

if __name__ == "__main__":
    run_regeneration()
