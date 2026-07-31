# +Ciclo Ingestion Agent: Raw Data Sanitation and Mapping 🚴‍♂️🧹

import os
import sys
import json
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from core.metadata_agent import generate_content_with_retry

class LLMSanitationRecipeSchema(BaseModel):
    archive_files: List[str] = Field(default=[], description="List of auxiliary filenames to move to the unused/ folder to prevent ambiguity (e.g. Manzanas, Macrozonas).")
    merge_output_name: Optional[str] = Field(None, description="If communes need merging, target output filename (e.g. Zonas_EOD_GV.shp).")
    merge_sources: List[str] = Field(default=[], description="If communes need merging, list of source shapefile names (e.g. ['Zonas_Valparaiso.shp', 'Zonas_Vina_del_Mar.shp']).")
    merge_id_cols: List[str] = Field(default=[], description="If communes need merging, list of zone ID column names in order matching merge_sources (e.g. ['ID_ZONA_12', 'ID_ZONA_1']).")
    column_mapping_keys: List[str] = Field(default=[], description="Detected non-standard column names that need mapping (e.g. ['ID_ZONA']).")
    column_mapping_values: List[str] = Field(default=[], description="Standard alias column names to map to, in order matching column_mapping_keys (e.g. ['eod_zona']).")
    filter_column: Optional[str] = Field(None, description="The attribute column name to filter on if external zones are detected (e.g. 'MACROZONA').")
    filter_operator: Optional[str] = Field(None, description="The filter operator: '==' or '!='.")
    filter_value: Optional[str] = Field(None, description="The value to filter by as a string (e.g. '9').")
    filter_reason: Optional[str] = Field(None, description="Explanatory reason why this filter is necessary (e.g. 'Excludes external zones to prevent OOM').")

class IngestionAgent:
    """
    IngestionAgent: Diagnoses raw folder structures and compiles Sanitation Recipes.
    Includes automatic prompt fallback to collect GEMINI_API_KEY if missing.
    """
    def __init__(self):
        self.api_key = self._acquire_api_key()
        self.client = genai.Client(api_key=self.api_key)

    def _acquire_api_key(self) -> str:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("\n[bold yellow]🔑 GEMINI API KEY IS REQUIRED FOR ACTIVE AGENT[/]")
            try:
                api_key = input("Enter your GEMINI_API_KEY (leave blank to exit): ").strip()
            except (KeyboardInterrupt, EOFError):
                api_key = ""
            
            if not api_key:
                print("[bold red]Error:[/] GEMINI_API_KEY is required for the Ingestion Agent. Ingestion aborted.")
                sys.exit(1)
            
            # Find and write to .env file in api/app/
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
            env_file_path = os.path.join(base_dir, ".env")
            try:
                with open(env_file_path, "a") as f:
                    f.write(f"\nGEMINI_API_KEY={api_key}\n")
                os.environ["GEMINI_API_KEY"] = api_key
                print("[bold green]Key saved successfully to configuration.[/]")
            except Exception as e:
                print(f"[Warning] Could not save key to .env: {e}")
                
        return api_key

    def generate_sanitation_recipe(self, city_key: str, files_list: List[str], schemas: Dict[str, List[str]], error_message: str) -> Optional[SanitationRecipe]:
        """
        Queries Gemini to inspect the files and schemas, returning a structured Sanitation Recipe.
        """
        system_instructions = """
        You are an expert urban planning and geospatial data agent. Your task is to inspect the file structure
        and column schemas of a city's raw zones directory, identify ingestion anomalies (ambiguity,
        fragmented commune files, missing zone ID headers), and compile a structured SanitationRecipe.
        
        Rules:
        - If multiple shapefiles (.shp) exist, find the ones that are auxiliary/unused (like Macrozonas or Manzanas) and add their filenames to 'archive_files'.
        - If the city zones are split into separate commune shapefiles, specify how to merge them using 'merge_output_name', 'merge_sources', and 'merge_id_cols'.
        - If a column contains the Zone ID (e.g. ID_ZONA, id_zona, idzona) but is not named 'eod_zona' or 'zona', map it using 'column_mapping_keys' and 'column_mapping_values'.
        - If the dataset has external zones or massive spatial scope outliers (e.g. causing OOM or massive hexagon counts), identify the attribute defining the external boundary (like MACROZONA or DESCRIPCIO) and generate a filter block using 'filter_column', 'filter_operator', 'filter_value', and 'filter_reason' (e.g. filter_column='MACROZONA', filter_operator='!=', filter_value='9', filter_reason='Excludes external zones to prevent OOM').
        - Do NOT include any nested objects in the JSON schema to prevent API validation errors. Keep all schema fields flat as defined.
        """
        
        prompt = f"""
        City Key: {city_key}
        Available Files in raw zones: {files_list}
        Schemas (Columns per file): {json.dumps(schemas, indent=2)}
        Ingestion Error encountered: {error_message}
        """
        
        try:
            response = generate_content_with_retry(
                self.client,
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instructions,
                    response_mime_type="application/json",
                    response_schema=LLMSanitationRecipeSchema,
                    temperature=0.0
                )
            )
            recipe = LLMSanitationRecipeSchema.model_validate_json(response.text)
            return recipe
        except Exception as e:
            print(f"[IngestionAgent Error] Failed to generate sanitation recipe: {e}")
            return None

    def audit_and_sanitize(self, city_key: str, city_meta: dict, zones_shp_path: str, demand_folder: str, zones_folder: str, yes: bool = False) -> bool:
        """
        Performs the Pre-flight Ingestion Hygiene Check.
        Compares bounding boxes, flags scope mismatches, compiles a Sanitation Recipe,
        and executes the cleanup upon user approval.
        """
        import geopandas as gpd
        import shutil
        
        print(f"🧹 [Ingestion Hygiene] Auditing data boundaries for '{city_key}'...")
        
        # 1. Spatial Scope Check
        try:
            gdf = gpd.read_file(zones_shp_path)
        except Exception as e:
            print(f"[Ingestion Hygiene Error] Could not read shapefile: {e}")
            return False
            
        if gdf.empty:
            print(f"[Ingestion Hygiene Error] Shapefile is empty: {zones_shp_path}")
            return False
            
        # Get registry area
        bbox_w = city_meta.get('bbox_w', 0.0)
        bbox_s = city_meta.get('bbox_s', 0.0)
        bbox_e = city_meta.get('bbox_e', 0.0)
        bbox_n = city_meta.get('bbox_n', 0.0)
        registry_area = abs(bbox_e - bbox_w) * abs(bbox_n - bbox_s)
        
        if registry_area == 0:
            print("[Ingestion Hygiene Warning] Expected city bounding box is zero. Skipping spatial scope check.")
            return True
            
        # Reproject to WGS84 to compare area in degrees squared
        gdf_wgs84 = gdf.to_crs(epsg=4326)
        xmin, ymin, xmax, ymax = gdf_wgs84.total_bounds
        shp_area = abs(xmax - xmin) * abs(ymax - ymin)
        
        ratio = shp_area / registry_area if registry_area > 0 else 0
        
        if ratio > 5.0:
            print(f"\n⚠️  [WARNING] Spatial Scope Mismatch Detected for '{city_key}':")
            print(f"   - Expected City Bounding Box Area: {registry_area:.6f} sq. degrees")
            print(f"   - Shapefile Bounding Box Area: {shp_area:.6f} sq. degrees ({ratio:.1f}x larger)")
            print(f"   - Diagnostic: Bounding box exceeds limit. External zones are likely included, risking memory exhaustion (OOM).")
            
            # Extract schemas and file lists for the agent
            files_list = os.listdir(zones_folder)
            schemas = {
                os.path.basename(zones_shp_path): gdf.columns.tolist()
            }
            error_message = f"SPATIAL_SCOPE_ANOMALY: Bounding box is {ratio:.1f}x larger than expected city bounds. Outer/external zones detected."
            
            print("🤖 Ingestion Agent is analyzing dataset to generate a Sanitation Recipe...")
            recipe = self.generate_sanitation_recipe(city_key, files_list, schemas, error_message)
            
            if not recipe or not recipe.filter_column:
                print("✕ Ingestion Agent failed to propose a valid filtering recipe. Proceeding with caution.")
                return True
                
            print("\n📋 PROPOSED SANITATION RECIPE:")
            print(f"   - Filter Column: '{recipe.filter_column}'")
            print(f"   - Operation:     Keep rows where {recipe.filter_column} {recipe.filter_operator} '{recipe.filter_value}'")
            print(f"   - Reason:        {recipe.filter_reason}")
            
            # Interactive Approval (Consent Gate)
            approved = yes
            if not approved:
                if sys.stdin.isatty():
                    try:
                        ans = input(f"\nApply this Sanitation Recipe to {os.path.basename(zones_shp_path)}? (y/n): ").strip().lower()
                        approved = ans in ['y', 'yes']
                    except (KeyboardInterrupt, EOFError):
                        approved = False
                else:
                    print("✕ Stdin is not a TTY. Skipping recipe application.")
                    approved = False
                    
            if approved:
                print("⚙ Applying Sanitation Recipe...")
                col = recipe.filter_column
                op = recipe.filter_operator
                val = recipe.filter_value
                
                # Filter rows
                try:
                    # Parse numerical value if possible
                    try:
                        val_parsed = int(val)
                    except ValueError:
                        try:
                            val_parsed = float(val)
                        except ValueError:
                            val_parsed = val
                            
                    if op == '==':
                        filtered_gdf = gdf[gdf[col] == val_parsed]
                    elif op == '!=':
                        filtered_gdf = gdf[gdf[col] != val_parsed]
                    else:
                        print(f"✕ Unsupported operator '{op}' in recipe.")
                        return False
                        
                    # Save a backup of the original shapefile before modifying it
                    unused_dir = os.path.join(zones_folder, "unused")
                    os.makedirs(unused_dir, exist_ok=True)
                    print(f"   - Archiving original shapefile components to {unused_dir}...")
                    
                    base_name = os.path.splitext(os.path.basename(zones_shp_path))[0]
                    for ext in ['.shp', '.dbf', '.shx', '.prj', '.qpj', '.cpg', '.sbn', '.sbx', '.shp.xml']:
                        f_src = os.path.join(zones_folder, base_name + ext)
                        if os.path.exists(f_src):
                            # Copy to unused/ as backup
                            shutil.copy2(f_src, os.path.join(unused_dir, base_name + "_original" + ext))
                            
                    # Save the filtered shapefile back to zones_shp_path
                    filtered_gdf.to_file(zones_shp_path)
                    print(f"✓ Cleaned shapefile saved successfully with {len(filtered_gdf)} zones (original had {len(gdf)}).")
                    return True
                except Exception as e:
                    print(f"✕ Failed to apply filter recipe: {e}")
                    return False
            else:
                print("✕ Recipe application declined by user. Proceeding without modification.")
                
        return True


class PreflightDiagnosticAuditor:
    """
    +Ciclo Pre-flight Diagnostic Auditor (IngestionOntology v1)
    Audits raw datasets in data/[city]/raw/, classifies files under IngestibilityStatus,
    renders the Rich terminal diagnostic report panel, and compiles an executable SanitationRecipe.
    """
    def audit_city_raw_directory(
        self,
        city_key: str,
        city_meta: dict,
        data_base_path: str,
        target_srid: int = 4326,
        yes: bool = False
    ) -> Optional["SanitationRecipe"]:
        """
        Audits raw files in data/[city]/raw/, checks spatial CRS, column aliases,
        census scope, and renders the diagnostic report panel.
        """
        import geopandas as gpd
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich.text import Text
        from core.ontology import (
            IngestibilityStatus, SpatialSanityType, SchemaAlignmentType,
            SanitationActionType, FileDiagnosticReport, SanitationRecipe
        )

        console = Console()
        raw_dir = os.path.join(data_base_path, "data", city_key, "raw")
        zones_dir = os.path.join(raw_dir, f"{city_key}_zones")
        demand_dir = os.path.join(raw_dir, f"{city_key}_demand")
        census_path = os.path.join(raw_dir, f"{city_key}_census.parquet")

        reports: List[FileDiagnosticReport] = []
        overall_verdict = IngestibilityStatus.INGESTABLE_READY
        column_mapping = {}
        archive_files = []
        reproject_files = []
        census_clip_path = None
        use_osm_fallback = False

        # --- 1. Audit Administrative Zones Shapefile ---
        if os.path.exists(zones_dir):
            shp_files = [f for f in os.listdir(zones_dir) if f.endswith(".shp")]
            if len(shp_files) > 1:
                # Mark non-primary shapefiles for archiving
                primary_shp = [f for f in shp_files if "zona" in f.lower() or "zone" in f.lower()]
                target = primary_shp[0] if primary_shp else shp_files[0]
                for auxiliary in shp_files:
                    if auxiliary != target:
                        archive_files.append(auxiliary)
            elif len(shp_files) == 1:
                target = shp_files[0]
            else:
                target = None

            if target:
                full_shp_path = os.path.join(zones_dir, target)
                try:
                    gdf = gpd.read_file(full_shp_path)
                    cols = gdf.columns.tolist()
                    detected_crs = str(gdf.crs) if gdf.crs else "None"
                    
                    actions = []
                    issues = []
                    status = IngestibilityStatus.INGESTABLE_READY
                    
                    # CRS Check
                    if gdf.crs and gdf.crs.to_epsg() != target_srid:
                        actions.append(SanitationActionType.REPROJECT_CRS)
                        issues.append(f"CRS is {detected_crs} (Expected EPSG:{target_srid})")
                        reproject_files.append(target)
                        status = IngestibilityStatus.INGESTABLE_REPAIRABLE

                    # Column Alias Check
                    alias_found = False
                    for col in cols:
                        if col.lower() in ['id_zona', 'zona_id', 'idzona', 'num_zona'] and col != 'zone_id':
                            column_mapping[col] = 'zone_id'
                            alias_found = True
                    if alias_found:
                        actions.append(SanitationActionType.REMAP_COLUMNS)
                        issues.append(f"Non-standard Zone ID headers detected ({list(column_mapping.keys())})")
                        status = IngestibilityStatus.INGESTABLE_REPAIRABLE

                    reports.append(FileDiagnosticReport(
                        filename=target,
                        filepath=full_shp_path,
                        status=status,
                        spatial_sanity=SpatialSanityType.CRS_REPROJECT_NEEDED if SanitationActionType.REPROJECT_CRS in actions else SpatialSanityType.CRS_MATCH,
                        schema_alignment=SchemaAlignmentType.ALIAS_MAPPABLE if alias_found else SchemaAlignmentType.CANONICAL_KEYS_PRESENT,
                        detected_crs=detected_crs,
                        detected_columns=cols,
                        proposed_actions=actions,
                        issues_summary=issues
                    ))
                    if status == IngestibilityStatus.INGESTABLE_REPAIRABLE:
                        overall_verdict = IngestibilityStatus.INGESTABLE_REPAIRABLE
                except Exception as e:
                    reports.append(FileDiagnosticReport(
                        filename=target,
                        filepath=full_shp_path,
                        status=IngestibilityStatus.NON_INGESTABLE_UNRELATED,
                        issues_summary=[f"Could not read shapefile: {e}"]
                    ))
                    overall_verdict = IngestibilityStatus.NON_INGESTABLE_UNRELATED

        # --- 2. Audit OD Matrix Files ---
        if os.path.exists(demand_dir):
            od_files = [f for f in os.listdir(demand_dir) if f.endswith(".csv") or f.endswith(".parquet")]
            if od_files:
                od_target = od_files[0]
                od_full_path = os.path.join(demand_dir, od_target)
                try:
                    import pandas as pd
                    if od_target.endswith(".csv"):
                        od_df = pd.read_csv(od_full_path, nrows=10)
                    else:
                        od_df = pd.read_parquet(od_full_path)
                    cols = od_df.columns.tolist()
                    actions = []
                    issues = []
                    status = IngestibilityStatus.INGESTABLE_READY
                    
                    alias_found = False
                    for col in cols:
                        if col.lower() in ['origen', 'id_origen'] and col != 'origin':
                            column_mapping[col] = 'origin'
                            alias_found = True
                        elif col.lower() in ['destino', 'id_destino'] and col != 'destination':
                            column_mapping[col] = 'destination'
                            alias_found = True
                        elif col.lower() in ['viajes', 'cant_viajes'] and col != 'trips':
                            column_mapping[col] = 'trips'
                            alias_found = True

                    if alias_found:
                        actions.append(SanitationActionType.REMAP_COLUMNS)
                        issues.append(f"Non-standard OD matrix column headers detected ({list(column_mapping.keys())})")
                        status = IngestibilityStatus.INGESTABLE_REPAIRABLE

                    reports.append(FileDiagnosticReport(
                        filename=od_target,
                        filepath=od_full_path,
                        status=status,
                        schema_alignment=SchemaAlignmentType.ALIAS_MAPPABLE if alias_found else SchemaAlignmentType.CANONICAL_KEYS_PRESENT,
                        detected_columns=cols,
                        proposed_actions=actions,
                        issues_summary=issues
                    ))
                    if status == IngestibilityStatus.INGESTABLE_REPAIRABLE:
                        overall_verdict = IngestibilityStatus.INGESTABLE_REPAIRABLE
                except Exception as e:
                    reports.append(FileDiagnosticReport(
                        filename=od_target,
                        filepath=od_full_path,
                        status=IngestibilityStatus.NON_INGESTABLE_UNRELATED,
                        issues_summary=[f"Could not read OD matrix file: {e}"]
                    ))

        # --- 3. Audit Census Dataset ---
        if os.path.exists(census_path):
            try:
                import pandas as pd
                census_df = pd.read_parquet(census_path)
                cols = census_df.columns.tolist()
                actions = []
                issues = []
                status = IngestibilityStatus.INGESTABLE_READY
                
                # Check population column aliases
                pop_alias = None
                for col in cols:
                    if col.lower() in ['n_per', 'personas', 'poblacion', 'ind_pob', 'pop'] and col != 'pop_total':
                        pop_alias = col
                        column_mapping[col] = 'pop_total'
                        break
                if pop_alias:
                    actions.append(SanitationActionType.REMAP_COLUMNS)
                    issues.append(f"Population column '{pop_alias}' mapped to 'pop_total'")
                    status = IngestibilityStatus.INGESTABLE_REPAIRABLE

                # Check Spatial Scope for Nationwide Census
                if 'census_2024_pais' in census_path or len(census_df) > 50000:
                    actions.append(SanitationActionType.CENSUS_BBOX_CLIP)
                    issues.append("Nationwide census dataset detected (>50,000 rows). Spatial BBOX clipping required.")
                    census_clip_path = census_path
                    status = IngestibilityStatus.INGESTABLE_REPAIRABLE

                reports.append(FileDiagnosticReport(
                    filename=os.path.basename(census_path),
                    filepath=census_path,
                    status=status,
                    detected_columns=cols,
                    proposed_actions=actions,
                    issues_summary=issues
                ))
                if status == IngestibilityStatus.INGESTABLE_REPAIRABLE:
                    overall_verdict = IngestibilityStatus.INGESTABLE_REPAIRABLE
            except Exception as e:
                reports.append(FileDiagnosticReport(
                    filename=os.path.basename(census_path),
                    filepath=census_path,
                    status=IngestibilityStatus.NON_INGESTABLE_UNRELATED,
                    issues_summary=[f"Corrupted census parquet file: {e}"]
                ))
        else:
            # Missing Census Fallback
            use_osm_fallback = True
            reports.append(FileDiagnosticReport(
                filename=f"{city_key}_census.parquet",
                filepath=census_path,
                status=IngestibilityStatus.INGESTABLE_REPAIRABLE,
                proposed_actions=[SanitationActionType.FALLBACK_OSM_RESIDENTIAL],
                issues_summary=["Census dataset missing. Will fall back to OSM residential building footprints."]
            ))
            overall_verdict = IngestibilityStatus.INGESTABLE_REPAIRABLE

        # --- 4. Render Rich Diagnostic Panel ---
        table = Table(title="Dataset Ingestibility Diagnostic Breakdown", border_style="cyan", show_header=True, header_style="bold magenta")
        table.add_column("Filename", style="bold white", width=25)
        table.add_column("Status", width=22)
        table.add_column("Proposed Sanitation Actions", width=35)
        table.add_column("Issues & Notes", width=35)

        for rep in reports:
            if rep.status == IngestibilityStatus.INGESTABLE_READY:
                status_txt = "[bold green]INGESTABLE_READY 🟢[/]"
            elif rep.status == IngestibilityStatus.INGESTABLE_REPAIRABLE:
                status_txt = "[bold yellow]REPAIRABLE 🟡[/]"
            else:
                status_txt = "[bold red]NON_INGESTABLE 🔴[/]"

            actions_txt = ", ".join([a.value for a in rep.proposed_actions]) if rep.proposed_actions else "None"
            issues_txt = " | ".join(rep.issues_summary) if rep.issues_summary else "Schema 100% compliant"
            table.add_row(rep.filename, status_txt, actions_txt, issues_txt)

        panel_title = f"[bold cyan]+CICLO PRE-FLIGHT INGESTION DIAGNOSTIC REPORT: {city_key.upper()}[/]"
        panel = Panel(table, title=panel_title, border_style="bold green" if overall_verdict == IngestibilityStatus.INGESTABLE_READY else "bold yellow")
        console.print(panel)

        recipe = SanitationRecipe(
            city_key=city_key,
            target_srid=target_srid,
            verdict=overall_verdict,
            file_reports=reports,
            archive_files=archive_files,
            column_mapping=column_mapping,
            reproject_files=reproject_files,
            census_bbox_clip=census_clip_path,
            use_osm_residential_fallback=use_osm_fallback
        )

        return recipe


class SanitationRecipeExecutor:
    """
    Executes approved Sanitation Recipes (reprojecting CRS, remapping columns,
    clipping nationwide census files to city BBOX + 15km buffer, and archiving auxiliary shapefiles).
    """
    @staticmethod
    def execute_recipe(recipe: SanitationRecipe, data_base_path: str, bbox: Optional[List[float]] = None) -> bool:
        """Applies all sanitation transformations defined in the recipe."""
        import geopandas as gpd
        import pandas as pd
        import shutil

        city_key = recipe.city_key
        raw_dir = os.path.join(data_base_path, "data", city_key, "raw")
        proc_dir = os.path.join(data_base_path, "data", city_key, "proc")
        zones_dir = os.path.join(raw_dir, f"{city_key}_zones")
        unused_dir = os.path.join(raw_dir, "unused")
        os.makedirs(proc_dir, exist_ok=True)

        print(f"⚙ [SanitationExecutor] Executing Sanitation Recipe for '{city_key}' (Verdict: {recipe.verdict.value})...")

        # 1. Archive Auxiliary Files
        if recipe.archive_files:
            os.makedirs(unused_dir, exist_ok=True)
            for filename in recipe.archive_files:
                src = os.path.join(zones_dir, filename)
                if os.path.exists(src):
                    base = os.path.splitext(filename)[0]
                    for ext in ['.shp', '.dbf', '.shx', '.prj', '.qpj', '.cpg']:
                        f_ext = os.path.join(zones_dir, base + ext)
                        if os.path.exists(f_ext):
                            shutil.move(f_ext, os.path.join(unused_dir, base + ext))
                    print(f"   ✓ Archived auxiliary file: {filename} -> unused/")

        # 2. Shapefile Reprojection & Column Remapping
        if recipe.reproject_files or recipe.column_mapping:
            if os.path.exists(zones_dir):
                shp_files = [f for f in os.listdir(zones_dir) if f.endswith('.shp')]
                for shp_name in shp_files:
                    shp_path = os.path.join(zones_dir, shp_name)
                    try:
                        gdf = gpd.read_file(shp_path)
                        modified = False
                        
                        if recipe.column_mapping:
                            rename_map = {k: v for k, v in recipe.column_mapping.items() if k in gdf.columns}
                            if rename_map:
                                gdf = gdf.rename(columns=rename_map)
                                print(f"   ✓ Renamed shapefile columns in {shp_name}: {rename_map}")
                                modified = True
                                
                        if shp_name in recipe.reproject_files and recipe.target_srid:
                            print(f"   - [Reproject] Transforming {shp_name} to EPSG:{recipe.target_srid}...")
                            gdf = gdf.to_crs(epsg=recipe.target_srid)
                            modified = True
                            
                        if modified:
                            gdf.to_file(shp_path)
                            print(f"   ✓ Saved updated shapefile {shp_name}.")
                    except Exception as shp_err:
                        print(f"   ✕ Failed updating shapefile {shp_name}: {shp_err}")

        # 3. Census BBOX Spatial Clipping
        if recipe.census_bbox_clip and os.path.exists(recipe.census_bbox_clip) and bbox is not None:
            try:
                print(f"   - [Census BBOX Clip] Clipping nationwide census dataset to city buffer $+ 15km$...")
                c_df = pd.read_parquet(recipe.census_bbox_clip)
                
                # Apply column renaming if present
                if recipe.column_mapping:
                    c_df = c_df.rename(columns=recipe.column_mapping)

                # Filter spatially using BBOX + 15km (0.15 deg buffer)
                xmin, ymin, xmax, ymax = bbox
                buffer_deg = 0.15
                xmin, ymin, xmax, ymax = xmin - buffer_deg, ymin - buffer_deg, xmax + buffer_deg, ymax + buffer_deg
                
                if 'geometry' in c_df.columns:
                    try:
                        from shapely.geometry import box
                        bbox_box = box(xmin, ymin, xmax, ymax)
                        mask = c_df['geometry'].apply(lambda g: g is not None and g.intersects(bbox_box))
                        c_df = c_df[mask]
                    except Exception:
                        pass
                elif 'lat' in c_df.columns and 'lon' in c_df.columns:
                    mask = (c_df['lon'] >= xmin) & (c_df['lon'] <= xmax) & (c_df['lat'] >= ymin) & (c_df['lat'] <= ymax)
                    c_df = c_df[mask]

                proc_census_path = os.path.join(proc_dir, "census.parquet")
                c_df.to_parquet(proc_census_path)
                print(f"   ✓ Clipped census dataset saved to {proc_census_path} ({len(c_df)} rows).")
            except Exception as e:
                print(f"   ✕ Census BBOX clipping failed: {e}")

        print("✓ [SanitationExecutor] Recipe execution completed successfully.")
        return True

