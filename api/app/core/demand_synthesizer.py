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
        
        # Identify ID column case-insensitively
        id_col = None
        candidates = ['zona', 'zona_eod', 'zonas_eod', 'id_zona', 'id', 'objectid']
        for col in zones_gdf.columns:
            if col.lower() in candidates:
                id_col = col
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
            
        h3_gdf['eod_zona'] = pd.to_numeric(h3_gdf['eod_zona'], errors='coerce').fillna(0).astype(int)
        
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
        
        # Identify purpose columns dynamically (columns starting with 'trips_')
        purpose_cols = [c for c in od_macro.columns if c.startswith('trips_') and c != 'trips']

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
            for col in purpose_cols:
                m_chunk[col] = m_chunk[col] * m_chunk['w_o'] * m_chunk['w_d']
            
            output_cols = ['h3_origin', 'h3_dest', 'trips'] + purpose_cols
            m_chunk = m_chunk[m_chunk['trips'] > 0.1][output_cols]
            
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
        
        # Check for ID column case-insensitively
        id_col = None
        candidates = ['zona', 'zona_eod', 'zonas_eod', 'id_zona', 'id', 'objectid']
        for col in zones.columns:
            if col.lower() in candidates:
                id_col = col
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
        Generic extractor for SECTRA MDB/ACCDB databases.
        Joins Viaje and Persona tables to get expanded trips.
        Optimized to prevent OOM on metropolitan datasets.
        '''
        import subprocess
        import csv
        print(f"   - [Synthesizer] Extracting macro OD from {os.path.basename(mdb_path)}...")
        
        # 1. Check if Viaje has factor column directly to avoid loading Persona table (OOM prevention)
        v_fieldnames = []
        try:
            cmd_v = f'mdb-export "{mdb_path}" Viaje'
            proc_v_header = subprocess.Popen(['bash', '-c', cmd_v], stdout=subprocess.PIPE, text=True)
            header_line = proc_v_header.stdout.readline()
            if header_line:
                v_fieldnames = [name.strip() for name in header_line.split(',')]
            proc_v_header.terminate()
            proc_v_header.wait()
        except Exception:
            pass
            
        v_cols = {c.lower(): c for c in v_fieldnames} if v_fieldnames else {}
        
        factor_candidates = ['factor', 'factor_expansion', 'factorexpansion', 'factor_exp']
        v_factor_col = None
        for cand in factor_candidates:
            if v_cols.get(cand):
                v_factor_col = v_cols.get(cand)
                break
                
        factors = {}
        if not v_factor_col:
            print("   - [Synthesizer] Direct factor column not found in Viaje table. Loading Persona table factors (fallback)...")
            try:
                # Get headers first to resolve column names dynamically
                cmd_hdr = f'mdb-export "{mdb_path}" Persona'
                proc_hdr = subprocess.Popen(['bash', '-c', cmd_hdr], stdout=subprocess.PIPE, text=True)
                header_line = proc_hdr.stdout.readline()
                proc_hdr.terminate()
                proc_hdr.wait()
                
                if not header_line:
                    raise ValueError("Failed to retrieve Persona table headers.")
                    
                fieldnames = [name.strip() for name in header_line.split(',')]
                p_cols = {c.lower(): c for c in fieldnames}
                
                f_col = p_cols.get('factor') or p_cols.get('factor_expansion')
                f_weekday_col = p_cols.get('factor_laboralnormal') or p_cols.get('factorlaboralnormal')
                id_f = p_cols.get('idfolio') or p_cols.get('hogar') or p_cols.get('folio')
                id_p = p_cols.get('idpersona') or p_cols.get('persona')
                
                if not id_f or not id_p:
                    raise KeyError(f"Could not find Hogar/IdFolio or Persona/IdPersona columns in Persona table. Columns: {fieldnames}")
                
                # Build and execute dynamic SELECT query to load only the resolved columns
                select_cols = [id_f, id_p]
                if f_col: select_cols.append(f_col)
                if f_weekday_col: select_cols.append(f_weekday_col)
                
                cols_sql = ", ".join([f'"{c}"' for c in select_cols])
                sql_query = f"SELECT {cols_sql} FROM Persona;"
                
                cmd_p = f'echo "{sql_query}" | mdb-sql -P -H -d "," "{mdb_path}"'
                proc_p = subprocess.Popen(['bash', '-c', cmd_p], stdout=subprocess.PIPE, text=True)
                
                import csv
                reader_p = csv.reader(proc_p.stdout)
                
                for row in reader_p:
                    if len(row) >= 2:
                        hogar = row[0].strip()
                        persona = row[1].strip()
                        
                        factor_val = 1.0
                        # If weekday factor is selected and available
                        if f_weekday_col and len(row) >= len(select_cols) and row[-1].strip():
                            factor_val = float(row[-1].strip())
                        # Otherwise if general factor is selected and available
                        elif f_col and len(row) >= 3 and row[2].strip():
                            factor_val = float(row[2].strip())
                            
                        factors[(hogar, persona)] = factor_val
                        
                proc_p.wait()
            except Exception as e:
                print(f"   - [Warning] Factor extraction failed: {e}. Using 1.0 fallback.")
        else:
            print(f"   - [Synthesizer] Found direct factor column '{v_factor_col}' in Viaje table. Bypassing Persona join to prevent OOM.")

        # 2. Extract and Expand Trips
        matrix = {}
        purpose_mapping = {
            '1': 'trips_work',
            '2': 'trips_study',
            '3': 'trips_shopping',
            '4': 'trips_personal',
            '5': 'trips_recreational',
            '6': 'trips_returning_home'
        }
        
        try:
            cmd_v = f'mdb-export "{mdb_path}" Viaje'
            proc_v = subprocess.Popen(['bash', '-c', cmd_v], stdout=subprocess.PIPE, text=True)
            reader_v = csv.DictReader(proc_v.stdout)
            v_cols = {c.lower(): c for c in reader_v.fieldnames}
            o_col = v_cols.get('zonaorigen') or v_cols.get('zona_origen') or v_cols.get('origen')
            d_col = v_cols.get('zonadestino') or v_cols.get('zona_destino') or v_cols.get('destino')
            vid_f = v_cols.get('idfolio') or v_cols.get('hogar') or v_cols.get('folio')
            vid_p = v_cols.get('idpersona') or v_cols.get('persona')
            
            # Find purpose column if it exists
            prop_col = None
            for cand in ['proposito', 'proposito_viaje', 'proposito_via', 'prop']:
                if v_cols.get(cand):
                    prop_col = v_cols.get(cand)
                    break
            
            if not o_col or not d_col:
                raise KeyError(f"Missing ZonaOrigen/ZonaDestino columns in Viaje table. Columns: {list(v_cols.values())}")
            if not v_factor_col and (not vid_f or not vid_p):
                raise KeyError(f"Missing Hogar/IdFolio or Persona/IdPersona columns in Viaje table (needed for Persona join). Columns: {list(v_cols.values())}")
            
            for row in reader_v:
                o, d = row[o_col], row[d_col]
                
                if v_factor_col:
                    val = row[v_factor_col]
                    f = float(val) if val else 1.0
                else:
                    f = factors.get((row[vid_f], row[vid_p]), 1.0)
                    
                prop = row.get(prop_col, '').strip() if prop_col else ''
                purpose_key = purpose_mapping.get(prop)
                
                if (o, d) not in matrix:
                    matrix[(o, d)] = {'total': 0.0}
                    if prop_col:
                        for pk in purpose_mapping.values():
                            matrix[(o, d)][pk] = 0.0
                
                matrix[(o, d)]['total'] += f
                if prop_col and purpose_key:
                    matrix[(o, d)][purpose_key] += f
            
            # Save to temp macro CSV
            with open(output_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                header = ['Zona_Origen', 'Zona_Destino', 'Viajes_Totales']
                active_purposes = []
                if prop_col:
                    # Only output purpose columns that actually received trips
                    for pk in purpose_mapping.values():
                        total_p_trips = sum(item[pk] for item in matrix.values())
                        if total_p_trips > 0.0:
                            active_purposes.append(pk)
                    header.extend(active_purposes)
                
                writer.writerow(header)
                for (o, d), data in matrix.items():
                    row_data = [o, d, data['total']]
                    for pk in active_purposes:
                        row_data.append(data[pk])
                    writer.writerow(row_data)
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
