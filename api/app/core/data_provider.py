import os
import json
import zipfile
import pandas as pd
import geopandas as gpd
from typing import Dict, Optional
from core.demand_synthesizer import DemandSynthesizer
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
        Includes projects/ folder for scenario testing.
        '''
        for sub in ['raw', 'raw/projects', 'proc', 'out/maps', 'out/qgis']:
            os.makedirs(f"data/{city_key}/{sub}", exist_ok=True)
        print(f"   - [Structure] Initialized encapsulated workspace for '{city_key}'.")

    def satisfy_demand_matrix(self, city_key: str, srid: int, od_input_override: Optional[str] = None) -> str:
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

        # NESTED CONVENTIONAL PATHING: data/[city]/raw/[city]_demand/demand.mdb
        demand_source = f"{raw_dir}/{city_key}_demand/demand.mdb"
        zones_source = f"{raw_dir}/{city_key}_zones/zones.shp"

        if os.path.exists(demand_source) and os.path.exists(zones_source):
            # Extract into proc/
            proc_zones_dir = f"{proc_dir}/convention_zones"
            os.makedirs(proc_zones_dir, exist_ok=True)
            
            # Synthesize
            synth = DemandSynthesizer(srid=int(srid), h3_resolution=self.h3_level)
            macro_od_path = f"{proc_dir}/od_matrix_macro.csv"
            
            synth.extract_macro_od_from_mdb(demand_source, macro_od_path)
            h3_grid = synth.prepare_h3_grid(gpd.read_file(zones_source))
            h3_enriched = synth.inject_census_population(h3_grid, census_path, gpd.read_file(zones_source))
            synth.disaggregate_od_matrix(h3_enriched, macro_od_path, potential_od)
            
            return potential_od
        else:
            instructions = f"DATA_MISSING: {city_key}. Please place 'demand.mdb' in {raw_dir}/{city_key}_demand/ " \
                           f"and 'zones.shp' (+ components) in {raw_dir}/{city_key}_zones/"
            diagnostic_handler.report("INGESTION_PAUSED", "ERROR", instructions)
            raise RuntimeError(instructions)
