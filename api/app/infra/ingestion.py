import os
import pandas as pd
import geopandas as gpd
import osmnx as ox
from shapely.geometry import Polygon
from h3 import h3
import geojson
import json
from infra.database import create_conn, df_to_postgres, check_table_existence
from infra.metadata import metadata_audit
from ui.components import diagnostic_handler

def read_any_spatial_file(file_path, bbox=None):
    if file_path.endswith('.parquet'):
        return gpd.read_parquet(file_path, bbox=tuple(bbox) if bbox is not None else None)
    elif file_path.endswith('.csv'):
        return pd.read_csv(file_path)
    else:
        return gpd.read_file(file_path)

def create_abbreviation(area):
    words = area.split(", ")
    abbreviation = "".join([word[:4].lower() for word in words])
    return abbreviation

def get_bbox_from_data(file_path, srid):
    if file_path.endswith('.geojson') or file_path.endswith('.json'):
        df = gpd.read_file(file_path)
        df_4326 = df.to_crs(epsg=4326)
        return df_4326.total_bounds
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

def download_osm(area, srid, type_network, bbox=None):
    if bbox is not None:
        west, south, east, north = bbox
        print(f"Downloading OSM data using demand BBOX: {bbox}")
        graph = ox.graph_from_bbox(north, south, east, west, network_type='all', truncate_by_edge=True)
    else:
        print(f"Downloading OSM data using location name: {area}")
        graph = ox.graph_from_place(area, network_type='all')
    
    edges = ox.graph_to_gdfs(graph, nodes=False, edges=True)
    nodes = ox.graph_to_gdfs(graph, nodes=True, edges=False) 
    
    if type_network == 'deshinibitor':
        usable = ['traffic_signals']
        features = nodes[nodes['highway'].isin(usable)]
    else:
        lines = edges[edges['geometry'].geom_type == 'LineString']
        if type_network == 'osm':
            usable = ['residential', 'primary', 'secondary', 'tertiary']
        elif type_network == 'bike':
            usable = ['cycleway']
        else:
            usable = ['primary', 'secondary', 'tertiary']
        features = lines[lines['highway'].isin(usable)]
        
    features = features.to_crs(epsg=srid)
    if len(features) == 0:
        raise ValueError(f"CRITICAL ERROR: No segments found for {type_network} in this area.")
    return features

def extract_h3_grid_from_od(od_file_path, h3_table_name, srid, user, password, host, port, database_name):
    df_od = pd.read_csv(od_file_path)
    
    # Audit metadata to find actual column names
    mapping = metadata_audit("SECTRA_EOD", df_od.columns.tolist())
    h3_o_col = mapping.get('h3_origin', 'h3_origin')
    h3_d_col = mapping.get('h3_dest', 'h3_dest')

    if h3_o_col not in df_od.columns or h3_d_col not in df_od.columns:
        raise KeyError(f"CRITICAL: Could not find H3 columns in OD file. Expected aliases for 'h3_origin' and 'h3_dest'. Found mapping: {mapping}")

    h3_o = set(df_od[h3_o_col].unique())
    h3_d = set(df_od[h3_d_col].unique())
    unique_h3 = h3_o.union(h3_d)
    count = len(unique_h3)
    geometry = [Polygon(h3.h3_to_geo_boundary(h, geo_json=True)) for h in unique_h3]
    h3_gdf = gpd.GeoDataFrame({'h3_index': list(unique_h3), 'geometry': geometry}, crs="EPSG:4326")
    h3_gdf = h3_gdf.to_crs(epsg=srid)
    from sqlalchemy import create_engine
    engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{database_name}')
    h3_gdf.to_postgis(name=h3_table_name, con=engine, if_exists='replace')
    return count

def download_h3(base_table, h3_table_name, srid, res, user, password, host, port, database_name):
    from sqlalchemy import create_engine
    engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{database_name}')
    sql = f'SELECT geometry as geom from {base_table}'
    df = gpd.read_postgis(sql,engine)
    df = df.to_crs(epsg=srid)
    df_4326 = df.to_crs(epsg=4326)
    west, south, east, north = df_4326.total_bounds
    polygon_geojson = geojson.Feature(geometry=Polygon([(west, south), (east, south), (east, north), (west, north)]), properties={})
    polygon_dict = json.loads(geojson.dumps(polygon_geojson.geometry))
    h3_hexagons = h3.polyfill(polygon_dict, res=int(res), geo_json_conformant=True)
    geometry = [Polygon(h3.h3_to_geo_boundary(h, geo_json=True)) for h in h3_hexagons]
    h3_hexagons_gdf = gpd.GeoDataFrame({'h3_index': list(h3_hexagons), 'geometry': geometry}, crs="EPSG:4326")
    h3_hexagons_gdf = h3_hexagons_gdf.to_crs(epsg=srid)
    h3_hexagons_gdf.to_postgis(name=h3_table_name, con=engine, if_exists='replace')

def handle_path_argument(type_network, path_arg, base_file_path, table_name, location_input, geom_type, srid, user, password, host, port, database_name, bbox=None):
    conn = create_conn(database_name, host, port, user, password)

    if path_arg is None or path_arg == 'None':
        print(f'Skipping {type_network} as no input was provided.')
        return

    if path_arg == '':
        if check_table_existence(conn, table_name):
            print(f'Table {table_name} already exists, skipping import.')
        else:
            df_osm = read_any_spatial_file(base_file_path)
            df_to_postgres(df_osm, table_name, geom_type, srid=srid, user=user, password=password, host=host, port=port, database_name=database_name)

    elif path_arg == 'osm':
        df_osm = download_osm(location_input, srid, type_network, bbox=bbox)
        df_to_postgres(df_osm, table_name, geom_type, srid=srid, user=user, password=password, host=host, port=port, database_name=database_name)

    else:
        df = read_any_spatial_file(path_arg, bbox=bbox)
        type_to_schema = {'census': 'INE_CENSO_2024', 'od': 'SECTRA_EOD'}
        source_type = type_to_schema.get(type_network)
        mapping = {}
        if source_type:
            mapping = metadata_audit(source_type, df.columns.tolist())
        if mapping:
            if 'trips' in mapping and 'expansion_factor' in mapping:
                t_col, e_col = mapping['trips'], mapping['expansion_factor']
                df[t_col] = df[t_col] * df[e_col]
                diagnostic_handler.report("DEMAND_SCALING", "INFO", f"Scaled {t_col} by {e_col}.")
            rename_dict = {v: k for k, v in mapping.items()}
            df = df.rename(columns=rename_dict)

        if 'geometry' in df.columns and geom_type == 'LineString':
            types = df.geometry.type.unique()
            if 'MultiLineString' in types:
                df = df.explode(index_parts=True)

        df_to_postgres(df, table_name, geom_type, srid=srid, user=user, password=password, host=host, port=port, database_name=database_name)
