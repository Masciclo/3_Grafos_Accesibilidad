# +Ciclo Engine: Demand-Based Routing Orchestrator 🚴‍♂️⚙️

import os
import sys
import argparse
import select
import time
import threading
from dotenv import load_dotenv
import pandas as pd
import geopandas as gpd
from rich.console import Console
from rich.live import Live
from rich.prompt import Confirm
from rich.panel import Panel

# Modular Imports
from ui.dashboard import PipelineUI, RichProgressAdapter, console
from ui.components import diagnostic_handler
from infra.database import create_conn, execute_query, check_table_existence
from infra.ingestion import handle_path_argument, create_abbreviation
from infra.metadata import metadata_audit, validate_hygienic_invariant
from core.scenario import ScenarioEngine
from core.pipeline import ScenarioConfig
from core.data_provider import DataProvider
from core.telemetry import telemetry_manager

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
import json
from core.academic_maps import AcademicMapGenerator

def main():
    parser = argparse.ArgumentParser(description='+Ciclo: Advanced Demand-Based Routing Simulation')
    # ... (parser arguments remain same)
    parser.add_argument("--location", dest="location", type=str, help="City name(s) or BBOX.")
    parser.add_argument("--scenario_id", dest="scenario_id", type=str, default="v1")
    parser.add_argument("--srid", dest="srid", type=str, help="Coordinate system. Optional if city is in semantic map.")
    parser.add_argument("--osm_input", dest="osm_input", type=str, default="osm")
    parser.add_argument("--ciclo_input", dest="ciclo_input", type=str)
    parser.add_argument("--od_input", dest="od_input", type=str)
    parser.add_argument("--census_input", dest="census_input", type=str, default="data/shared/census/chl/census_2024_pais.parquet")
    parser.add_argument("--projects_input", dest="projects_input", type=str)
    parser.add_argument("--reference_scenario", dest="reference_scenario", type=str)
    parser.add_argument("--yes", dest="force_yes", action="store_true")
    parser.add_argument("--cleanup", dest="cleanup", action="store_true")
    parser.add_argument("--mapping", dest="mapping", action="store_true", default=True, help="Generate interactive academic map suite.")
    parser.add_argument("--buffer_size", dest="buffer_size", type=int, default=15)
    parser.add_argument("--ref_snap_dist", dest="ref_snap_dist", type=float, default=5.0, help="Reference Snapping Distance (buffer size to align streets to project)")
    parser.add_argument("--parent_lineage_dist", dest="parent_lineage_dist", type=float, default=7.0, help="Parent Lineage Distance (search radius to map refactored segments back to baseline)")
    parser.add_argument("--project_influence_dist", dest="project_influence_dist", type=float, default=25.0, help="Project Influence Distance (clipping buffer size around project for audit)")
    parser.add_argument("--imp_primary", dest="imp_primary", type=float, default=15.0)
    parser.add_argument("--imp_secondary", dest="imp_secondary", type=float, default=7.0)
    parser.add_argument("--imp_tertiary", dest="imp_tertiary", type=float, default=3.0)
    parser.add_argument("--imp_local", dest="imp_local", type=float, default=1.5)
    parser.add_argument("--imp_bike", dest="imp_bike", type=float, default=0.5)
    parser.add_argument("--inhibit", dest="inhibit", type=int, default=1)
    parser.add_argument("--disinhibit", dest="disinhibit", type=int, default=1)
    parser.add_argument("--recommendation", dest="recommendation", type=str, help="Natural language prompt for AI-assisted cycleway design recommendations")
    parser.add_argument("--rec_sample_size", dest="rec_sample_size", type=int, default=1000, help="Uniform sample size of active OD pairs to accelerate greedy optimization")

    args = parser.parse_args()
    args.machine_hash = telemetry_manager.machine_hash # Inject for UI

    # --- Phase 12: Interactive Session Loop ---
    # Initialize Infrastructure
    db_config = {'name': DATABASE_NAME, 'host': HOST, 'port': PORT, 'user': USER, 'password': PASSWORD}
    engine = ScenarioEngine(db_config, sql_base_path, data_base_path)
    
    # Load Master Registry (CSV)
    registry_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'infra', 'city_registry.csv')
    census_base = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data', 'shared', 'census')
    
    provider = DataProvider(registry_path, census_base, h3_level=int(H3_LEVEL or 9))

    # Flag to check if we should exit after one run (CLI mode) or keep looping (Interactive mode)
    interactive_mode = args.location is None

    while True:
        # Step 0: Consultation / Initial Prompt
        if args.location is None:
            temp_ui = PipelineUI("Initial Boot", "0000", args=args)
            with Live(temp_ui.get_landing_layout(prompt_text="[bold yellow]ESPERANDO CONSULTA... PEGA O ESCRIBE ABAJO[/]"), refresh_per_second=10, console=console) as live:
                from rich.prompt import Prompt
                import re
                raw_query = Prompt.ask("[bold green]+ciclo[/]").strip()
                
                if raw_query.lower() in ['exit', 'quit', 'q']:
                    break

                loc_match = re.search(r'--location\s*=\s*["\']?([^"\'\s]+)["\']?', raw_query)
                if loc_match:
                    args.location = loc_match.group(1).strip()
                else:
                    noise = ['docker', 'exec', 'it', 'python', 'python3', 'main.py', 'grafos-accesibilidad-ciclo-py-1', 'ciclo-py']
                    clean_words = [w for w in raw_query.replace('\\', ' ').split() if not w.startswith('-') and w.lower() not in noise]
                    args.location = clean_words[0] if clean_words else "valdivia"
            
            args.force_yes = False
            args.scenario_id = "v13" 

        # Step 1: Logo Animation (Plays for every run)
        temp_ui = PipelineUI("Booting Scenario", "0000", args=args)
        # Use raw ANSI play_intro for 100% color fidelity
        temp_ui.animator.play_intro(loops=1)

        locations = [loc.strip() for loc in args.location.split(",")]
        
        for current_loc in locations:
            city_key = current_loc.split(',')[0].strip().lower()
            city_meta = provider.get_city_meta(city_key)
            if not city_meta:
                if not sys.stdin.isatty():
                    console.print(f"[bold red]Error:[/] City '{city_key}' is not registered and stdin is not a TTY. Cannot launch Wizard.")
                    sys.exit(1)
                city_meta = provider.bootstrap_new_city(city_key)
                if not city_meta:
                    console.print(f"[bold red]Skipping unregistered city '{city_key}'...[/]")
                    continue

            target_loc = city_meta.get("osm_name", current_loc)
            # --- SRID Resolution ---
            raw_srid = city_meta.get("srid", args.srid)
            if raw_srid is None or str(raw_srid).lower() == 'none' or str(raw_srid).strip() == '':
                target_srid = 4326
            else:
                try:
                    target_srid = int(raw_srid)
                except ValueError:
                    target_srid = 4326
            
            study_area_bbox = city_meta.get("bbox")

            # --- ExecutionCacheManager: Purge temporary city logs from previous uncommitted runs ---
            from core.execution_logger import ExecutionCacheManager
            ExecutionCacheManager.purge_temporary_logs(data_base_path, city_key)

            # --- IngestionOntology v1: Pre-flight Data Sanitation Audit ---
            try:
                from core.agents.ingestion_agent import PreflightDiagnosticAuditor, SanitationRecipeExecutor
                auditor = PreflightDiagnosticAuditor()
                recipe = auditor.audit_city_raw_directory(city_key, city_meta, data_base_path, target_srid=target_srid, yes=args.force_yes)
                if recipe and recipe.verdict != "INGESTABLE_READY":
                    SanitationRecipeExecutor.execute_recipe(recipe, data_base_path, bbox=study_area_bbox)
            except Exception as audit_err:
                console.print(f"[bold yellow]Pre-flight Audit Note:[/] {audit_err}")

            # --- DataProvider: Satisfy Pre-requisites ---
            try:
                validated_od = provider.satisfy_demand_matrix(city_key, target_srid, od_input_override=args.od_input, yes=args.force_yes)
            except Exception as e:
                console.print(f"[bold red]DataProvider Error:[/] {str(e)}")
                continue

            # --- SCREEN 2: Audit & Guard ---
            if not args.force_yes:
                ui = PipelineUI(target_loc, target_srid, args=args)
                census_columns = []
                if args.census_input and args.census_input.endswith('.parquet'):
                    import pyarrow.parquet as pq
                    census_columns = pq.read_schema(args.census_input).names
                od_columns = pd.read_csv(validated_od, nrows=5).columns.tolist()
                census_map = metadata_audit("INE_CENSO_2024", census_columns)
                od_map = metadata_audit("SECTRA_EOD", od_columns)

                # --- Task 13.1: Hygienic Invariant Enforcement ---
                is_census_clean, missing_census = validate_hygienic_invariant("INE_CENSO_2024", census_map.keys())
                is_od_clean, missing_od = validate_hygienic_invariant("SECTRA_EOD", od_map.keys())

                spatial_status = "VALID"
                if study_area_bbox:
                    try:
                        sample_h3 = pd.read_csv(validated_od, nrows=1)['h3_origin'].iloc[0]
                        import h3
                        lat, lon = h3.h3_to_coords(sample_h3)
                        if not (study_area_bbox[0] <= lon <= study_area_bbox[2] and study_area_bbox[1] <= lat <= study_area_bbox[3]):
                            spatial_status = "MISMATCH"
                    except: pass

                # --- Screen 2: Phase Budget & Audit ---
                ui = PipelineUI(target_loc, target_srid, args=args)
                
                # Pre-calculate ETAs for the Audit screen (Budget View)
                has_p = True if args.projects_input else False
                stage_keys = {1: 'ingestion', 2: 'topo', 3: 'grid', 5: 'refactor', 7: 'routing', 8: 'agg', 9: 'final'}
                for p in ui.phases:
                    key = stage_keys.get(p["id"])
                    if key:
                        pred = telemetry_manager.predict_eta(args.osm_input, validated_od, has_p, stage=key)
                        p["eta"] = telemetry_manager.format_eta(pred)

                # Render the static audit layout
                console.print(ui.get_audit_layout(census_map, od_map, spatial_status))
                
                from rich.prompt import Prompt
                choice = Prompt.ask("[bold yellow]What would you like to do? (C: Continue, R: Redefine)[/]", choices=["C", "c", "R", "r"], show_choices=False).upper()
                
                if choice == "R":
                    args.location = None 
                    break
                
                if args.location is None: break 
                
                # --- Hard Stop: Hygienic Invariant Violation ---
                if not is_census_clean or not is_od_clean:
                    console.print("[bold red]Fatal Ingestion Failure:[/] Hygienic Invariant Violated.")
                    if missing_census: console.print(f"   - Missing Census attributes: [bold]{', '.join(missing_census)}[/]")
                    if missing_od: console.print(f"   - Missing OD attributes: [bold]{', '.join(missing_od)}[/]")
                    args.location = None
                    break

                if spatial_status == "MISMATCH":
                    console.print("[bold red]Hard Stop:[/] Spatial anchoring guard triggered.")
                    args.location = None
                    break

            # --- AI Recommendation Engine Activation Hook ---
            if args.recommendation:
                if not args.reference_scenario:
                    console.print("[bold red]Error:[/] The --recommendation flag requires a --reference_scenario (e.g. --reference_scenario=current) to run.")
                    sys.exit(1)
                
                api_key = os.getenv("GEMINI_API_KEY")
                if not api_key:
                    console.print("\n[bold yellow]🔑 GEMINI API KEY IS REQUIRED FOR ACTIVE AGENT[/]")
                    try:
                        api_key = input("Enter your GEMINI_API_KEY (leave blank to exit): ").strip()
                    except (KeyboardInterrupt, EOFError):
                        api_key = ""
                    if not api_key:
                        console.print("[bold red]Error:[/] GEMINI_API_KEY not provided. Recommendation engine aborted.")
                        sys.exit(1)
                    
                    env_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), ".env")
                    try:
                        with open(env_file_path, "a") as f:
                            f.write(f"\nGEMINI_API_KEY={api_key}\n")
                        os.environ["GEMINI_API_KEY"] = api_key
                        console.print("[bold green]Key saved successfully to configuration.[/]")
                    except Exception as e:
                        console.print(f"[bold red]Warning:[/] Could not save key to .env: {e}")
                
                console.print(f"\n[bold green]🤖 INITIALIZING AI RECOMMENDATION AGENT FOR: {target_loc}[/]")
                from core.recommendation import RecommendationEngine
                rec_engine = RecommendationEngine(db_config, data_base_path, target_loc, target_srid)
                
                rec_geojson_path = rec_engine.run_recommendation_pipeline(
                    prompt=args.recommendation,
                    reference_scenario=args.reference_scenario,
                    sample_size=args.rec_sample_size,
                    study_area_bbox=study_area_bbox
                )
                
                if not rec_geojson_path:
                    console.print("[bold red]Recommendation failed to produce upgrade geometries. Aborting.[/]")
                    sys.exit(1)
                
                args.projects_input = rec_geojson_path
                args.scenario_id = "rec_" + os.path.basename(rec_geojson_path).replace(".geojson", "").split("_")[-1]
                console.print(f"[bold green]Auto-triggering project evaluation scenario: {args.scenario_id}[/]\n")

            # --- SCREEN 3: ScenarioEngine Execution ---
            config = ScenarioConfig(
                location=target_loc, city_key=city_key, scenario_id=args.scenario_id, srid=target_srid,
                osm_input=args.osm_input, od_input=validated_od, census_input=args.census_input,
                ciclo_input=args.ciclo_input, projects_input=args.projects_input,
                reference_scenario=args.reference_scenario, bbox=study_area_bbox,
                buffer_size=args.buffer_size, imp_primary=args.imp_primary,
                imp_secondary=args.imp_secondary, imp_tertiary=args.imp_tertiary,
                imp_local=args.imp_local, imp_bike=args.imp_bike,
                inhibit=bool(args.inhibit), disinhibit=bool(args.disinhibit),
                cleanup=args.cleanup, mapping=args.mapping,
                ref_snap_dist=args.ref_snap_dist,
                parent_lineage_dist=args.parent_lineage_dist,
                project_influence_dist=args.project_influence_dist
            )
            
            args.od_input = validated_od
            ui = PipelineUI(target_loc, target_srid, args=args)
            observer = RichProgressAdapter(ui)
            
            # Start Heartbeat for adaptive dashboard
            stop_heartbeat = threading.Event()
            def heartbeat():
                with Live(ui.get_dashboard_layout(), refresh_per_second=10, screen=False) as live:
                    while not stop_heartbeat.is_set():
                        live.update(ui.get_dashboard_layout())
                        time.sleep(0.5)
            
            h_thread = threading.Thread(target=heartbeat, daemon=True)
            h_thread.start()

            try:
                engine.run(config, observer)
                ui.completed = True
            except Exception as e:
                diagnostic_handler.report("PIPELINE_CRASH", "ERROR", str(e))
            finally:
                stop_heartbeat.set()
                h_thread.join(timeout=1)
                console.print(ui.get_dashboard_layout())

        # Post-execution logic
        if interactive_mode:
            # Task 13.8: Wait for user acknowledgment before returning to Screen 1
            Prompt.ask("\n[bold yellow]Analysis Completed. Press [ENTER] to return to the query console...[/]")
            args.location = None
        else:
            break

if __name__=='__main__':
    main()
