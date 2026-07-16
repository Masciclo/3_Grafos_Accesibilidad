import os
import geopandas as gpd
from core.demand_synthesizer import DemandSynthesizer

class SpatialSynthesizer:
    """
    Candidate 1 (Deepened): SpatialSynthesizer Module.
    Consolidates census data alignment, Shapefile loading, and H3 grid synthesis.
    Hides low-level geometry operations and file mappings behind one clean seam.
    """
    def __init__(self, srid: int, h3_resolution: int = 9):
        self.srid = srid
        self.h3_resolution = h3_resolution

    def synthesize_demand(self, demand_db_path: str, zones_shp_path: str, census_parquet_path: str, macro_od_output_path: str, final_micro_od_path: str) -> None:
        """
        Executes the full socio-spatial synthesis:
        1. Extracts the macro OD matrix from the SECTRA demand database.
        2. Prepares the H3 hexagonal grid from the study area zones.
        3. Enriches the hexagons with census population distribution.
        4. Disaggregates the macro trip matrix into micro origin-destination flows.
        """
        synth = DemandSynthesizer(srid=self.srid, h3_resolution=self.h3_resolution)
        
        # 1. Ingest macro-level OD data
        synth.extract_macro_od_from_mdb(demand_db_path, macro_od_output_path)
        
        # 2. Load zones shapefile and generate uniform H3 hexagonal grid
        zones_gdf = gpd.read_file(zones_shp_path)
        h3_grid = synth.prepare_h3_grid(zones_gdf)
        
        # 3. Align census blocks and distribute population onto H3 grid
        h3_enriched = synth.inject_census_population(h3_grid, census_parquet_path, zones_gdf)
        
        # 4. Generate micro-level demand matrices
        synth.disaggregate_od_matrix(h3_enriched, macro_od_output_path, final_micro_od_path)
