import geopandas as gpd
import pandas as pd
import h3
from shapely.geometry import Polygon
from shapely import wkb
import os
import sys

class DemandSynthesizer:
    '''
    Module 0: Socio-Functional Demand Synthesizer
    Translates Macro Data (Census Blocks, SECTRA Zones) into H3 Micro-Flows.
    '''
    def __init__(self, srid=32719, h3_resolution=9):
        self.srid = srid
        self.h3_resolution = h3_resolution

    def prepare_h3_grid(self, zones_gdf):
        '''
        Fills Macro Zones with H3 cells and maps the Zone ID to each cell.
        '''
        print(f"   - Generating H3 grid (Res {self.h3_resolution}) over {len(zones_gdf)} zones...")
        
        # --- Task: Naive Geometry Guard ---
        if zones_gdf.crs is None:
            print(f"   - Warning: Zones file has no CRS. Assuming EPSG:{self.srid}.")
            zones_gdf.crs = f"EPSG:{self.srid}"
        
        h3_indices = set()
        
        # Identify ID column
        id_col = None
        for candidate in ['Zona', 'ZONA_EOD', 'ID', 'OBJECTID']:
            if candidate in zones_gdf.columns:
                id_col = candidate
                break
        if not id_col:
            raise KeyError(f"Could not identify Zone ID in {zones_gdf.columns}")
        print(f"   - Identified '{id_col}' as the primary Zone ID.")

        # Ensure zones are in WGS84 for H3 polyfill
        zones_wgs84 = zones_gdf.to_crs(epsg=4326)
        
        for _, row in zones_wgs84.iterrows():
            poly = row.geometry
            if poly.geom_type == 'Polygon':
                polys = [poly]
            else:
                polys = list(poly.geoms)
            
            for p in polys:
                exterior = [(lat, lng) for lng, lat in p.exterior.coords]
                h3_indices.update(h3.polyfill_polygon(exterior, self.h3_resolution))
        
        h3_gdf = gpd.GeoDataFrame({
            'h3_index': list(h3_indices),
            'geometry': [Polygon([(lng, lat) for lat, lng in h3.h3_to_geo_boundary(idx, geo_json=False)]) for idx in h3_indices]
        }, crs="EPSG:4326")
        
        # Metric Join for high precision
        print(f"   - Mapping hexagons to parent macro-zones (Metric Join SRID {self.srid})...")
        h3_gdf_m = h3_gdf.to_crs(epsg=self.srid)
        zones_m = zones_gdf.to_crs(epsg=self.srid)
        
        h3_centroids = h3_gdf_m.copy()
        h3_centroids['geometry'] = h3_centroids.geometry.centroid
        joined = gpd.sjoin(h3_centroids, zones_m[[id_col, 'geometry']], how='left', predicate='intersects')
        
        # Resolve duplicates
        joined = joined.groupby(level=0).first()
        
        h3_gdf['eod_zona'] = joined[id_col].values # Align by index
        
        print(f"   - Hexagons before dropna: {len(h3_gdf)}")
        h3_gdf = h3_gdf.dropna(subset=['eod_zona'])
        print(f"   - Hexagons after mapping to zones: {len(h3_gdf)}")
        
        if len(h3_gdf) == 0:
            print("   - ERROR: No hexagons were mapped to zones. Check spatial overlap.")
            
        h3_gdf['eod_zona'] = h3_gdf['eod_zona'].astype(int)
        
        return h3_gdf

    def inject_census_population(self, h3_gdf, census_parquet_path, zones_gdf):
        '''
        Distributes population from census blocks to H3 cells using Area Proportional Overlay.
        '''
        if len(h3_gdf) == 0: return h3_gdf
        
        print("   - Loading and filtering Census blocks (with 10% safety buffer)...")
        zones_wgs84 = zones_gdf.to_crs(epsg=4326)
        xmin, ymin, xmax, ymax = zones_wgs84.total_bounds
        
        # Apply 10% Buffer to BBOX
        x_ext = (xmax - xmin) * 0.1
        y_ext = (ymax - ymin) * 0.1
        xmin, xmax = xmin - x_ext, xmax + x_ext
        ymin, ymax = ymin - y_ext, ymax + y_ext
        
        # Metadata-based BBOX filtering to save RAM
        df_meta = pd.read_parquet(census_parquet_path, columns=['SHAPE_bbox', 'n_per'])
        mask = df_meta['SHAPE_bbox'].apply(lambda b: not (b['xmin'] > xmax or b['xmax'] < xmin or b['ymin'] > ymax or b['ymax'] < ymin))
        relevant_indices = df_meta[mask].index
        
        print(f"   - Identified {len(relevant_indices)} blocks within expanded boundary.")
        df_full = pd.read_parquet(census_parquet_path, columns=['SHAPE', 'n_per']).loc[relevant_indices]
        
        # Decode WKB geometries
        geometries = [wkb.loads(g) for g in df_full['SHAPE']]
        census_gdf = gpd.GeoDataFrame(df_full, geometry=geometries, crs="EPSG:4326")
        
        print("   - Performing Mass Conservation Overlay (Population distribution)...")
        # Shift to Metric for area precision
        h3_m = h3_gdf.to_crs(epsg=self.srid)
        census_m = census_gdf.to_crs(epsg=self.srid)
        census_m['area_mz'] = census_m.geometry.area
        
        # Intersection
        intersection = gpd.overlay(h3_m, census_m[census_m['n_per'] > 0], how='intersection')
        intersection['pop_h3'] = (intersection.geometry.area / intersection['area_mz']) * intersection['n_per']
        
        h3_pop = intersection.groupby('h3_index')['pop_h3'].sum().reset_index()
        
        # Merge back to original H3 GDF
        final_h3 = h3_gdf.merge(h3_pop, on='h3_index', how='left').fillna(0)
        return final_h3

    def disaggregate_od_matrix(self, h3_enriched, od_macro_csv_path, output_path):
        '''
        Transforms Zone-to-Zone trips into Hex-to-Hex flows using Chunked Gravitational Disaggregation.
        Optimized for Metropolitan RAM limits.
        '''
        print("   - Loading Macro OD Matrix...")
        od_macro = pd.read_csv(od_macro_csv_path)
        od_macro['Zona_Origen'] = pd.to_numeric(od_macro['Zona_Origen'], errors='coerce').fillna(0).astype(int)
        od_macro['Zona_Destino'] = pd.to_numeric(od_macro['Zona_Destino'], errors='coerce').fillna(0).astype(int)
        
        # Calculate relative weights within zones
        zone_totals = h3_enriched.groupby('eod_zona')['pop_h3'].sum().reset_index()
        zone_totals.columns = ['eod_zona', 'total_pop_zona']
        h3_w = h3_enriched.merge(zone_totals, on='eod_zona', how='left')
        h3_w['weight'] = h3_w['pop_h3'] / (h3_w['total_pop_zona'] + 1e-6)
        
        h3_lookup = h3_w[['h3_index', 'eod_zona', 'weight']]
        
        print(f"   - Disaggregating {len(od_macro)} pairs in chunks to prevent OOM...")
        
        chunk_size = 1000
        first_chunk = True
        total_micro_pairs = 0
        
        for i in range(0, len(od_macro), chunk_size):
            chunk = od_macro.iloc[i:i+chunk_size]
            
            # Step 1: Merge Origins for this chunk
            m_chunk = chunk.merge(
                h3_lookup.rename(columns={'h3_index': 'h3_origin', 'weight': 'w_o', 'eod_zona': 'Zona_Origen'}),
                on='Zona_Origen'
            )
            
            # Step 2: Merge Destinations for this chunk
            m_chunk = m_chunk.merge(
                h3_lookup.rename(columns={'h3_index': 'h3_dest', 'weight': 'w_d', 'eod_zona': 'Zona_Destino'}),
                on='Zona_Destino'
            )
            
            # Step 3: Math and Filter
            m_chunk['trips'] = m_chunk['Viajes_Totales'] * m_chunk['w_o'] * m_chunk['w_d']
            m_chunk = m_chunk[m_chunk['trips'] > 0.1][['h3_origin', 'h3_dest', 'trips']]
            
            total_micro_pairs += len(m_chunk)
            
            # Step 4: Incremental Write
            mode = 'w' if first_chunk else 'a'
            header = True if first_chunk else False
            m_chunk.to_csv(output_path, mode=mode, index=False, header=header)
            
            first_chunk = False
            if (i // chunk_size) % 5 == 0:
                print(f"     * Processed {i + len(chunk)}/{len(od_macro)} macro-pairs...")

        print(f"✓ Micro Matrix synthesized successfully: {output_path} ({total_micro_pairs} micro-pairs)")
        return output_path

    def audit_inputs(self, zones_path, od_path, census_path):
        '''
        Audits datasets before processing to ensure integrity and spatial alignment.
        '''
        print("🔍 Stage: Input Data Audit...")
        
        # 1. Audit Zones
        zones = gpd.read_file(zones_path)
        if zones.empty:
            raise ValueError(f"CRITICAL: Zones file {zones_path} is empty.")
        
        # Check for ID column (using our flexible logic)
        id_col = None
        for candidate in ['Zona', 'ZONA_EOD', 'ID', 'OBJECTID']:
            if candidate in zones.columns:
                id_col = candidate
                break
        if not id_col:
            raise KeyError(f"AUDIT_FAIL: No Zone ID found in {zones.columns}")

        # 2. Audit OD Matrix
        od = pd.read_csv(od_path)
        if od.empty:
            raise ValueError(f"CRITICAL: OD Matrix {od_path} is empty.")
        
        # 3. Spatial Alignment Check
        # Does the OD matrix have zones that actually exist in the Shapefile?
        od_zones = set(pd.to_numeric(od['Zona_Origen'], errors='coerce').dropna().astype(int))
        shp_zones = set(zones[id_col].astype(int))
        intersection = od_zones.intersection(shp_zones)
        
        overlap_pct = (len(intersection) / len(od_zones)) * 100 if od_zones else 0
        print(f"   - Audit Results: ID Column='{id_col}', OD-SHP Overlap={overlap_pct:.1f}%")
        
        if overlap_pct < 10:
            raise ValueError(f"AUDIT_FAIL: Low spatial overlap ({overlap_pct:.1f}%). The OD data probably doesn't match this city's zonification.")
        
        print("✓ Audit Passed: Datasets are consistent.")
        return True

    def extract_macro_od_from_mdb(self, mdb_path, output_csv):
        '''
        Generic extractor for SECTRA MDB databases.
        Joins Viaje and Persona tables to get expanded trips.
        '''
        import subprocess
        import csv
        print(f"   - [Synthesizer] Extracting macro OD from {os.path.basename(mdb_path)}...")
        
        # 1. Get factors from Persona
        factors = {}
        try:
            cmd_p = f'mdb-export "{mdb_path}" Persona'
            proc_p = subprocess.Popen(['bash', '-c', cmd_p], stdout=subprocess.PIPE, text=True)
            reader_p = csv.DictReader(proc_p.stdout)
            p_cols = {c.lower(): c for c in reader_p.fieldnames}
            # Standard SECTRA keys
            f_col, id_f, id_p = p_cols.get('factor'), p_cols.get('idfolio'), p_cols.get('idpersona')
            
            for row in reader_p:
                factors[(row[id_f], row[id_p])] = float(row[f_col])
        except Exception as e:
            print(f"   - [Warning] Factor extraction failed: {e}. Using 1.0 fallback.")

        # 2. Extract and Expand Trips
        matrix = {}
        try:
            cmd_v = f'mdb-export "{mdb_path}" Viaje'
            proc_v = subprocess.Popen(['bash', '-c', cmd_v], stdout=subprocess.PIPE, text=True)
            reader_v = csv.DictReader(proc_v.stdout)
            v_cols = {c.lower(): c for c in reader_v.fieldnames}
            o_col, d_col = v_cols.get('zonaorigen'), v_cols.get('zonadestino')
            vid_f, vid_p = v_cols.get('idfolio'), v_cols.get('idpersona')
            
            for row in reader_v:
                o, d = row[o_col], row[d_col]
                f = factors.get((row[vid_f], row[vid_p]), 1.0)
                matrix[(o, d)] = matrix.get((o, d), 0) + f
            
            # Save to temp macro CSV
            with open(output_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Zona_Origen', 'Zona_Destino', 'Viajes_Totales'])
                for (o, d), t in matrix.items():
                    writer.writerow([o, d, t])
            return output_csv
        except Exception as e:
            raise RuntimeError(f"Failed to extract OD matrix: {e}")

if __name__ == "__main__":
    # ... rest of code
    if len(sys.argv) < 5:
        print("Usage: python demand_synthesizer.py <zones_shp> <census_parquet> <macro_csv> <output_csv>")
        sys.exit(1)
    
    synth = DemandSynthesizer()
    zones = gpd.read_file(sys.argv[1])
    h3_grid = synth.prepare_h3_grid(zones)
    h3_enriched = synth.inject_census_population(h3_grid, sys.argv[2], zones)
    synth.disaggregate_od_matrix(h3_enriched, sys.argv[3], sys.argv[4])
