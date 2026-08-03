import os
import json
import zipfile
import pandas as pd
import geopandas as gpd
from typing import Dict, Optional
from core.spatial_synthesizer import SpatialSynthesizer
from ui.components import diagnostic_handler

class DataProvider:
    """
    DataProvider: Deep module for data satisfying and autonomous demand synthesis.
    Supports CSV Master Registry for city metadata.
    """
    def __init__(self, registry_path: str, census_base_path: str, h3_level: int = 9):
        self.registry_path = registry_path
        self.census_base_path = census_base_path # e.g. data/shared/census/
        self.h3_level = h3_level
        self.registry = self._load_registry()

    def _load_registry(self) -> pd.DataFrame:
        if os.path.exists(self.registry_path):
            return pd.read_csv(self.registry_path)
        return pd.DataFrame()

    def get_city_meta(self, city_key: str) -> Optional[Dict]:
        if self.registry.empty: return None
        row = self.registry[self.registry['city_key'] == city_key]
        if not row.empty:
            meta = row.iloc[0].to_dict()
            # Reconstruct BBOX and other structured data
            meta['bbox'] = [meta['bbox_w'], meta['bbox_s'], meta['bbox_e'], meta['bbox_n']]
            meta['srid'] = meta['srid_default']
            return meta
        return None

    def initialize_location_structure(self, city_key: str):
        '''
        Task 13.5: Pre-emptive Folder Ghosting.
        Creates raw/, proc/, out/ immediately upon city request.
        Includes projects/, demand, and zones folders for scenario testing.
        '''
        for sub in [
            'raw', 'raw/projects', f'raw/{city_key}_demand', f'raw/{city_key}_zones', 
            'proc', 'out/maps', 'out/qgis'
        ]:
            os.makedirs(f"data/{city_key}/{sub}", exist_ok=True)
        print(f"   - [Structure] Initialized encapsulated workspace for '{city_key}'.")

    def bootstrap_new_city(self, city_key: str) -> Optional[Dict]:
        """
        Interactively bootstraps a new city key.
        Resolves spatial bounds and UTM zone projection using OSMnx/Nominatim.
        Appends metadata to city_registry.csv and creates directory structure.
        """
        from rich.prompt import Prompt, Confirm
        from rich.panel import Panel
        from rich.console import Console
        import osmnx as ox
        import glob
        
        console = Console()
        
        # Check if the raw directory structure exists
        raw_zones_dir = f"data/{city_key}/raw/{city_key}_zones"
        raw_demand_dir = f"data/{city_key}/raw/{city_key}_demand"
        folders_exist = os.path.exists(raw_zones_dir) and os.path.exists(raw_demand_dir)
        
        if not folders_exist:
            console.print(Panel(
                f"[bold yellow]CITY INGESTION WIZARD[/]\n"
                f"Key '[bold cyan]{city_key}[/]' is not registered in city_registry.csv.\n\n"
                f"We will create the required directory structure for this project.",
                border_style="yellow"
            ))
            confirm = Prompt.ask(
                f"[bold yellow]Would you like to create the folders under data/{city_key}/ now? (Y/N)[/]",
                choices=["Y", "N", "y", "n"],
                default="Y"
            ).upper()
            if confirm == "N":
                return None
                
            self.initialize_location_structure(city_key)
            console.print(Panel(
                f"[bold green]✓ Directory structure created successfully![/]\n\n"
                f"Please place your source files inside the following directories:\n"
                f"  1. Zones Shapefile (.shp + components) in:\n"
                f"     [bold cyan]{raw_zones_dir}/[/]\n"
                f"  2. Demand Database (.mdb) in:\n"
                f"     [bold cyan]{raw_demand_dir}/[/]\n\n"
                f"We will wait here until you place the files.",
                border_style="green"
            ))
            
            confirm_files = Prompt.ask(
                "[bold yellow]Have you placed the shapefile and database files in their respective folders? (Y/N)[/]",
                choices=["Y", "N", "y", "n"],
                default="Y"
            ).upper()
            if confirm_files == "N":
                return None
        else:
            console.print(Panel(
                f"[bold yellow]CITY INGESTION WIZARD[/]\n"
                f"Completing the registry for '[bold cyan]{city_key}[/]'.",
                border_style="yellow"
            ))
        
        xmin, ymin, xmax, ymax, srid = None, None, None, None, None
        osm_name = f"{city_key.capitalize()}, Chile"
        
        # Pre-emptive spatial auto-extraction from pre-placed Shapefiles
        shapefiles = glob.glob(f"{raw_zones_dir}/*.shp")
        if shapefiles:
            try:
                console.print(f"[bold green]✓ Found existing zones shapefile in raw/ folder:[/] {shapefiles[0]}")
                console.print("   - Auto-extracting spatial boundaries and projection...")
                zones_gdf = gpd.read_file(shapefiles[0])
                if not zones_gdf.empty:
                    # Project bounds to WGS84 (EPSG:4326) for OSM bounding box compatibility
                    zones_wgs84 = zones_gdf.to_crs(epsg=4326)
                    xmin, ymin, xmax, ymax = zones_wgs84.total_bounds
                    
                    # Calculate default UTM projection SRID from centroid
                    centroid = zones_wgs84.geometry.centroid.iloc[0]
                    lon, lat = centroid.x, centroid.y
                    utm_zone = int((lon + 180) / 6) + 1
                    srid = 32700 + utm_zone if lat < 0 else 32600 + utm_zone
                    
                    # Slightly pad the bounding box (5%) to capture surrounding network context
                    dx = xmax - xmin
                    dy = ymax - ymin
                    xmin -= dx * 0.05
                    xmax += dx * 0.05
                    ymin -= dy * 0.05
                    ymax += dy * 0.05
                    
                    osm_name = f"{city_key.capitalize()} (Auto-resolved from Shapefile)"
                    console.print(f"   - [Spatial Auto-Extraction] Resolved from Shapefile: BBOX=[{xmin:.4f}, {ymin:.4f}, {xmax:.4f}, {ymax:.4f}], Calculated SRID={srid}")
            except Exception as e:
                console.print(f"[bold yellow]! Spatial Auto-Extraction failed:[/] {e}. Falling back to OSM geocoder.")
                xmin = None
        else:
            console.print("[bold yellow]! No Shapefile found inside raw zones folder.[/] Falling back to OSM geocoder search.")
        
        if xmin is None:
            # 1. Ask for OSM Query String
            default_osm = f"{city_key.capitalize()}, Chile"
            osm_name = Prompt.ask("[bold green]OSM Location Query[/]", default=default_osm)
            
            # 2. Query Nominatim to resolve BBOX and Centroid
            console.print(f"Querying Nominatim Overpass API for [italic]{osm_name}[/]...")
            try:
                gdf = ox.geocoder.geocode_to_gdf(osm_name)
                if gdf.empty:
                    raise ValueError("No geometry returned.")
                    
                # Get BBOX
                xmin, ymin, xmax, ymax = gdf.total_bounds
                
                # Get Centroid
                centroid = gdf.geometry.centroid.iloc[0]
                lon, lat = centroid.x, centroid.y
                
                # Calculate UTM zone and SRID
                utm_zone = int((lon + 180) / 6) + 1
                srid = 32700 + utm_zone if lat < 0 else 32600 + utm_zone
                
                console.print(f"[bold green]✓ Resolved Bounds from OSM:[/] BBOX=[{xmin:.4f}, {ymin:.4f}, {xmax:.4f}, {ymax:.4f}], Calculated SRID={srid}")
            except Exception as e:
                console.print(f"[bold red]✕ OSM Lookup Failed:[/] {e}. Please input parameters manually.")
                xmin = float(Prompt.ask("Bounding Box West (xmin)"))
                ymin = float(Prompt.ask("Bounding Box South (ymin)"))
                xmax = float(Prompt.ask("Bounding Box East (xmax)"))
                ymax = float(Prompt.ask("Bounding Box North (ymax)"))
                srid = int(Prompt.ask("Projection SRID (e.g. 32719)", default="32719"))
            
        # 3. Ask for Country Code & Region ID
        country_code = Prompt.ask("[bold green]Country Code[/]", default="CHL").upper()
        ine_region = Prompt.ask("[bold green]INE Region ID (e.g. 13 for Santiago, 15 for Arica)[/]", default="13")
        
        # 4. Confirm write
        new_row = {
            'city_key': city_key,
            'country_code': country_code,
            'srid_default': srid,
            'osm_name': osm_name,
            'bbox_w': xmin,
            'bbox_s': ymin,
            'bbox_e': xmax,
            'bbox_n': ymax,
            'ine_region_id': ine_region
        }
        
        console.print("\n[bold cyan]Proposed Registry Row:[/]")
        for k, v in new_row.items():
            console.print(f"  [bold]{k}:[/] {v}")
            
        confirm_write = Prompt.ask(
            "[bold yellow]Would you like to write these parameters to city_registry.csv? (Y/N)[/]",
            choices=["Y", "N", "y", "n"],
            default="Y"
        ).upper()
        if confirm_write == "Y":
            # Append to registry
            df_new = pd.DataFrame([new_row])
            if os.path.exists(self.registry_path):
                df_new.to_csv(self.registry_path, mode='a', header=False, index=False)
            else:
                df_new.to_csv(self.registry_path, mode='w', header=True, index=False)
                
            # Reload registry in DataProvider
            self.registry = self._load_registry()
            
            # Create directories (ensures all subfolders exist)
            self.initialize_location_structure(city_key)
            
            console.print(f"[bold green]✓ Éxito:[/] Estructura de directorios encapsulados creada. Registro completo.")
            return self.get_city_meta(city_key)
            
        return None

    def satisfy_demand_matrix(self, city_key: str, srid: int, od_input_override: Optional[str] = None, yes: bool = False) -> str:
        """
        Ensures a demand matrix exists for the given city, synthesizing it if necessary.
        Conventional Path: data/[city]/proc/od_matrix_micro.csv
        """
        self.initialize_location_structure(city_key)
        
        city_dir = f"data/{city_key}"
        raw_dir = f"{city_dir}/raw"
        proc_dir = f"{city_dir}/proc"
        potential_od = f"{proc_dir}/od_matrix_micro.csv"
        
        # 1. If override provided, use it
        if od_input_override:
            return od_input_override
            
        # 2. Check for processed matrix
        if os.path.exists(potential_od):
            return potential_od
            
        # 3. Autonomous Synthesis (Módulo 0)
        city_meta = self.get_city_meta(city_key)
        if not city_meta:
            raise ValueError(f"CRITICAL: No entry for '{city_key}' in city_registry.csv. Please add the city metadata first.")

        diagnostic_handler.report("AUTO_INGEST", "INFO", f"Demand matrix missing for {city_key}. Attempting conventional synthesis...")
        
        # Determine Country-specific Census
        country = city_meta.get('country_code', 'CHL').lower()
        census_path = os.path.join(self.census_base_path, country, f"census_2024_pais.parquet")

        from infra.ingestion import resolve_single_file_by_extension

        # NESTED CONVENTIONAL PATHING: Scan dynamically for any .mdb / .shp inside the respective raw folders
        demand_folder = f"{raw_dir}/{city_key}_demand"
        zones_folder = f"{raw_dir}/{city_key}_zones"
        
        try:
            demand_source = resolve_single_file_by_extension(demand_folder, ('.mdb', '.accdb'))
            zones_source = resolve_single_file_by_extension(zones_folder, '.shp')
            files_exist = True
        except Exception:
            files_exist = False

        if files_exist:
            # Stage Ingestion Hygiene Check (General Spatial Scope Check)
            try:
                from core.agents.ingestion_agent import IngestionAgent
                hygiene_agent = IngestionAgent()
                # Run audit & sanitize
                hygiene_agent.audit_and_sanitize(
                    city_key=city_key,
                    city_meta=city_meta,
                    zones_shp_path=zones_source,
                    demand_folder=demand_folder,
                    zones_folder=zones_folder,
                    yes=yes
                )
            except Exception as e:
                print(f"[Ingestion Hygiene Warning] Bypassing active hygiene check: {e}")

            # Extract into proc/
            proc_zones_dir = f"{proc_dir}/convention_zones"
            os.makedirs(proc_zones_dir, exist_ok=True)
            
            # Synthesize using SpatialSynthesizer
            try:
                srid_val = int(srid)
            except (ValueError, TypeError):
                srid_val = 4326
                
            synthesizer = SpatialSynthesizer(srid=srid_val, h3_resolution=self.h3_level)
            macro_od_path = f"{proc_dir}/od_matrix_macro.csv"
            
            synthesizer.synthesize_demand(
                demand_db_path=demand_source,
                zones_shp_path=zones_source,
                census_parquet_path=census_path,
                macro_od_output_path=macro_od_path,
                final_micro_od_path=potential_od
            )
            
            return potential_od
        else:
            instructions = f"DATA_MISSING: {city_key}. Please place a database (.mdb or .accdb) file in {raw_dir}/{city_key}_demand/ " \
                           f"and a shapefile (.shp) file (+ components) in {raw_dir}/{city_key}_zones/"
            diagnostic_handler.report("INGESTION_PAUSED", "ERROR", instructions)
            raise RuntimeError(instructions)
