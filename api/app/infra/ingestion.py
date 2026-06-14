import os
import pandas as pd
import geopandas as gpd
import osmnx as ox
import fiona
from shapely.geometry import Polygon, shape, box
from shapely import wkb
from h3 import h3
import geojson
import json
from infra.database import create_conn, df_to_postgres, check_table_existence, stream_file_to_postgres
from infra.metadata import metadata_audit
from ui.components import diagnostic_handler

# --- Task: Bypass Rate Limits & Handle Scale ---
# Main Overpass server - Optimized with VPN and Precise BBOX
ox.settings.overpass_endpoint = "https://overpass-api.de/api/interpreter"
ox.settings.timeout = 600
ox.settings.requests_timeout = 600

def stream_geojson_to_db(file_path, table_name, geom_type, srid, user, password, host, port, database_name):
    # ... rest of code
    """
    Description: Streams features from a GeoJSON into PostGIS using chunks to prevent RAM exhaustion.
    """
    chunk_size = 5000
    with fiona.open(file_path) as src:
        chunk = []
        total_count = 0
        for feature in src:
            geom = shape(feature['geometry'])
            props = feature['properties']
            props['geometry'] = geom
            chunk.append(props)
            
            if len(chunk) >= chunk_size:
                df_chunk = gpd.GeoDataFrame(chunk, crs=src.crs)
                df_to_postgres(df_chunk, table_name, geom_type, srid, user, password, host, port, database_name, mode='append' if total_count > 0 else 'replace')
                total_count += len(chunk)
                print(f"Streamed {total_count} features...")
                chunk = []
        
        if chunk:
            df_chunk = gpd.GeoDataFrame(chunk, crs=src.crs)
            df_to_postgres(df_chunk, table_name, geom_type, srid, user, password, host, port, database_name, mode='append' if total_count > 0 else 'replace')

def read_any_spatial_file(file_path, bbox=None):
    if file_path.endswith('.parquet'):
        print(f"   - Reading Parquet: {file_path}")
        df = pd.read_parquet(file_path)
        
        # Manual BBOX filter using the pre-calculated bbox column
        if 'SHAPE_bbox' in df.columns and bbox is not None:
            xmin, ymin, xmax, ymax = bbox
            mask = df['SHAPE_bbox'].apply(lambda b: not (b['xmin'] > xmax or b['xmax'] < xmin or b['ymin'] > ymax or b['ymax'] < ymin))
            df = df[mask]
        
        # Decode WKB if necessary
        if 'SHAPE' in df.columns:
            geoms = [wkb.loads(g) for g in df['SHAPE']]
            # Remove raw binary column to avoid naming collisions during standardization
            df = df.drop(columns=['SHAPE'])
            gdf = gpd.GeoDataFrame(df, geometry=geoms, crs="EPSG:4326")
        else:
            gdf = gpd.GeoDataFrame(df)

        # 3. Clean non-SQL compatible columns (Dictionaries like SHAPE_bbox)
        for col in gdf.columns:
            if not gdf[col].empty and isinstance(gdf[col].iloc[0], dict):
                print(f"   - Dropping non-SQL column: {col}")
                gdf = gdf.drop(columns=[col])
        return gdf

    elif file_path.endswith('.csv'):
        return pd.read_csv(file_path)
    else:
        if bbox is not None:
            print(f"   - Filtering {os.path.basename(file_path)} with reprojected BBOX...")
            try:
                # 1. Detect File CRS without loading full data
                with fiona.open(file_path) as src:
                    file_crs = src.crs
                
                # 2. Reproject BBOX (WGS84 -> File CRS)
                from shapely.geometry import box
                bbox_gdf = gpd.GeoDataFrame({'geometry': [box(*bbox)]}, crs="EPSG:4326")
                bbox_native = bbox_gdf.to_crs(file_crs).total_bounds
                
                return gpd.read_file(file_path, bbox=tuple(bbox_native))
            except Exception as e:
                print(f"   - Warning: BBOX filtering failed ({e}). Loading full file.")
                return gpd.read_file(file_path)
                
        return gpd.read_file(file_path)

def create_abbreviation(area):
    # Sanitize input: remove symbols and handle BBOX numeric strings
    clean_area = "".join([c if c.isalnum() else "_" for c in area])
    
    # If the area is mostly numeric (BBOX), use a generic prefix
    if any(char.isdigit() for char in clean_area[:5]):
        return "area_bbox"

    words = area.split(", ")
    abbreviation = "".join([word[:4].lower() for word in words])
    return "".join([c for c in abbreviation if c.isalnum()]) # Final safety

def get_bbox_from_data(file_path, srid):
    if file_path.endswith('.geojson') or file_path.endswith('.json'):
        # HIGH PERF: Use fiona to get bounds without loading entire file
        with fiona.open(file_path) as src:
            west, south, east, north = src.bounds
            return west, south, east, north
    elif file_path.endswith('.parquet'):
        df = gpd.read_parquet(file_path)
        df_4326 = df.to_crs(epsg=4326)
        return df_4326.total_bounds
    elif file_path.endswith('.csv'):
        df = pd.read_csv(file_path)
        h3_col = 'h3_origin' if 'h3_origin' in df.columns else 'h3_index'
        if h3_col in df.columns:
            coords = [h3.h3_to_geo(h) for h in df[h3_col].unique()]
            lats, lons = zip(*coords)
            return min(lons), min(lats), max(lons), max(lats)
    return None

import osmnx as ox
# --- Task: Bypass Rate Limits & Handle Scale ---
# Main Overpass server - Optimized with VPN and Precise BBOX
ox.settings.overpass_endpoint = "https://overpass-api.de/api/interpreter"
ox.settings.timeout = 600
ox.settings.requests_timeout = 600

def download_osm(area, srid, type_network, bbox=None):
    # --- Priority 1: Explicit BBOX ---
    if bbox is not None:
        west, south, east, north = bbox
        print(f"   - [OSM] Downloading using explicit BBOX: {bbox}")
        graph = ox.graph_from_bbox(north, south, east, west, network_type='all', truncate_by_edge=True)
    else:
        # --- Priority 2: Try to extract BBOX from area string ---
        try:
            potential_bbox = [float(x.strip()) for x in area.split(',')]
            if len(potential_bbox) == 4:
                west, south, east, north = potential_bbox
                print(f"   - [OSM] Detected raw BBOX query: {potential_bbox}")
                graph = ox.graph_from_bbox(north, south, east, west, network_type='all', truncate_by_edge=True)
            else:
                raise ValueError
        except:
            # --- Priority 3: Fallback to Place Name ---
            print(f"   - [OSM] Downloading via location name: {area}")
            graph = ox.graph_from_place(area, network_type='all')
    
    edges = ox.graph_to_gdfs(graph, nodes=False, edges=True)
    lines = edges[edges['geometry'].geom_type == 'LineString'].copy()
    
    # --- Task: Semantic Bridge Mapping (#TS57) ---
    # We expand the whitelist to include EVERYTHING that provides urban connectivity
    if type_network == 'osm':
        # Whitelist
        usable = [
            'motorway', 'motorway_link', 'trunk', 'trunk_link', 
            'primary', 'primary_link', 'secondary', 'secondary_link', 
            'tertiary', 'tertiary_link', 'residential', 'living_street', 'unclassified'
        ]
        
        # Keep only usable streets
        lines = lines[lines['highway'].isin(usable)]
        
        # Mapper to consolidate into our 4 core road categories (for impedance)
        mapping = {
            'motorway': 'primary', 'motorway_link': 'primary',
            'trunk': 'primary', 'trunk_link': 'primary',
            'primary': 'primary', 'primary_link': 'primary',
            'secondary': 'secondary', 'secondary_link': 'secondary',
            'tertiary': 'tertiary', 'tertiary_link': 'tertiary',
            'residential': 'residential', 'living_street': 'residential',
            'unclassified': 'residential', 'road': 'residential', 'service': 'residential'
        }
        
        # New Whitelist including road and service for connectivity safety
        usable = list(mapping.keys())
        
        def normalize_highway(h):
            # 1. Handle lists from OSMnx (e.g. ['secondary', 'bridge'])
            if isinstance(h, list):
                # Search for the best match in our whitelist within the list
                matches = [mapping[tag] for tag in h if tag in mapping]
                if matches: return matches[0] # Return the most important tag found
                h = h[0] # Fallback to first item if no match
            
            # 2. Map single tag
            return mapping.get(h, 'residential')
            
        # First filter: identify rows that contain AT LEAST one usable tag
        def is_usable(h):
            if isinstance(h, list):
                return any(tag in usable for tag in h)
            return h in usable

        lines = lines[lines['highway'].apply(is_usable)]
        lines['highway'] = lines['highway'].apply(normalize_highway)
        
    elif type_network == 'bike':
        lines = lines[lines['highway'] == 'cycleway']
    
    return lines.to_crs(epsg=srid)

def extract_h3_grid_from_od(od_file_path, h3_table_name, srid, user, password, host, port, database_name, callback=None):
    if callback: callback(None, "ADVANCE_GRID", increment=10)
    df_od = pd.read_csv(od_file_path)
    if callback: callback(None, "ADVANCE_GRID", increment=10)
    
    mapping = metadata_audit("SECTRA_EOD", df_od.columns.tolist())
    h3_o_col = mapping.get('h3_origin', 'h3_origin')
    h3_d_col = mapping.get('h3_dest', 'h3_dest')

    if h3_o_col not in df_od.columns or h3_d_col not in df_od.columns:
        raise KeyError(f"CRITICAL: Could not find H3 columns in OD file. Expected aliases for 'h3_origin' and 'h3_dest'.")

    if callback: callback(None, "ADVANCE_GRID", increment=20)
    h3_o = set(df_od[h3_o_col].unique())
    h3_d = set(df_od[h3_d_col].unique())
    unique_h3 = h3_o.union(h3_d)
    count = len(unique_h3)
    # Ensure H3 identifiers are strings for the h3 library
    geometry = [Polygon(h3.h3_to_geo_boundary(str(h), geo_json=True)) for h in unique_h3]
    h3_gdf = gpd.GeoDataFrame({'h3_index': list(unique_h3), 'geometry': geometry}, crs="EPSG:4326")
    
    if callback: callback(None, "ADVANCE_GRID", increment=30)
    if h3_gdf.crs != f"EPSG:{srid}":
        print(f"   - [Reproject] Transforming H3 Grid from EPSG:4326 to EPSG:{srid}")
        h3_gdf = h3_gdf.to_crs(epsg=srid)
    
    from sqlalchemy import create_engine
    engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{database_name}')
    h3_gdf.to_postgis(name=h3_table_name, con=engine, if_exists='replace')
    if callback: callback(None, "ADVANCE_GRID", increment=30)
    return count

def download_h3(base_table, h3_table_name, srid, res, user, password, host, port, database_name, callback=None):
    """
    Description: Generates an exact H3 grid by polyfilling the actual geometries in the base table.
    """
    if callback: callback(None, "ADVANCE_GRID", increment=10)
    from sqlalchemy import create_engine
    engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{database_name}')
    
    # 1. Load the actual geometries from the base table
    sql = f'SELECT geometry FROM {base_table}'
    gdf = gpd.read_postgis(sql, engine, geom_col='geometry')
    if callback: callback(None, "ADVANCE_GRID", increment=20)
    
    # 2. Project to WGS84 for H3 library
    gdf_4326 = gdf.to_crs(epsg=4326)
    if callback: callback(None, "ADVANCE_GRID", increment=10)
    
    h3_indices = set()
    for geom in gdf_4326.geometry:
        if geom.is_empty: continue
        
        # Convert geometry to GeoJSON-like dict for polyfill
        if geom.geom_type == 'MultiPolygon':
            for poly in geom.geoms:
                polygon_dict = json.loads(geojson.dumps(poly))
                h3_indices.update(h3.polyfill(polygon_dict, res=int(res), geo_json_conformant=True))
        else:
            polygon_dict = json.loads(geojson.dumps(geom))
            h3_indices.update(h3.polyfill(polygon_dict, res=int(res), geo_json_conformant=True))
    
    if callback: callback(None, "ADVANCE_GRID", increment=30)
            
    # 3. Create GeoDataFrame
    geometry = [Polygon(h3.h3_to_geo_boundary(h, geo_json=True)) for h in h3_indices]
    h3_gdf = gpd.GeoDataFrame({'h3_index': list(h3_indices), 'geometry': geometry}, crs="EPSG:4326")
    if callback: callback(None, "ADVANCE_GRID", increment=10)
    
    # 4. Reproject and Upload
    if h3_gdf.crs != f"EPSG:{srid}":
        print(f"   - [Reproject] Transforming H3 Grid from EPSG:4326 to EPSG:{srid}")
        h3_gdf = h3_gdf.to_crs(epsg=srid)
    
    if callback: callback(None, "ADVANCE_GRID", increment=10)
    h3_gdf.to_postgis(name=h3_table_name, con=engine, if_exists='replace')
    if callback: callback(None, "ADVANCE_GRID", increment=10)
    print(f"   - [Grid] Generated {len(h3_indices)} hexagons covering the {base_table} geometry.")

def handle_path_argument(type_network, path_arg, base_file_path, table_name, location_input, geom_type, srid, user, password, host, port, database_name, bbox=None):
    conn = create_conn(database_name, host, port, user, password)
    if path_arg is None or path_arg == 'None': return

    # STRATEGY: High-Performance Ogr2ogr Streaming for large GeoJSON
    if isinstance(path_arg, str) and os.path.exists(path_arg) and os.path.getsize(path_arg) > 50 * 1024 * 1024 and not path_arg.endswith('.parquet'):
        diagnostic_handler.report("HIGH_PERF_INGESTION", "INFO", f"Streaming large file via ogr2ogr: {os.path.basename(path_arg)}")
        if stream_file_to_postgres(path_arg, table_name, srid, user, password, host, port, database_name):
            return 

    if path_arg == '':
        if check_table_existence(conn, table_name): return
        df = read_any_spatial_file(base_file_path)
    elif path_arg == 'osm':
        df = download_osm(location_input, srid, type_network, bbox=bbox)
    else:
        df = read_any_spatial_file(path_arg, bbox=bbox)
        
    # --- 1.5. Target SRID Handshake (Scientific Integrity) ---
    if hasattr(df, 'crs') and df.crs is not None:
        if df.crs != f"EPSG:{srid}":
            print(f"   - [Reproject] Transforming {type_network} from {df.crs} to EPSG:{srid}")
            df = df.to_crs(epsg=srid)
    
    # --- 2. Metadata Audit & Standardization ---
    type_to_schema = {'census': 'INE_CENSO_2024', 'od': 'SECTRA_EOD'}
    schema_name = type_to_schema.get(type_network)
    if schema_name:
        mapping = metadata_audit(schema_name, df.columns.tolist())
        if mapping:
            # Special case for OD Matrix: expand trips if factors exist
            if 'trips' in mapping and 'expansion_factor' in mapping:
                print("   - Expanding trips using expansion factor...")
                df[mapping['trips']] = pd.to_numeric(df[mapping['trips']], errors='coerce') * pd.to_numeric(df[mapping['expansion_factor']], errors='coerce')
            
            # Perform renaming: {raw_name: internal_standard}
            rename_map = {v: k for k, v in mapping.items() if v != k}
            
            # Robustness: prevent GeoPandas collision if renaming a column to 'geometry' 
            # while 'geometry' already exists (e.g. from Parquet conversion)
            if 'geometry' in rename_map.values() and 'geometry' in df.columns:
                rename_map = {k: v for k, v in rename_map.items() if v != 'geometry'}
            
            if rename_map:
                print(f"   - Standardizing columns for {type_network}: {rename_map}")
                df = df.rename(columns=rename_map)

    # --- 3. Geometry Explode & Upload ---
    if 'geometry' in df.columns:
        if 'MultiLineString' in df.geometry.type.unique() or 'MultiPolygon' in df.geometry.type.unique():
            df = df.explode(index_parts=True)

    df_to_postgres(df, table_name, geom_type, srid=srid, user=user, password=password, host=host, port=port, database_name=database_name)
