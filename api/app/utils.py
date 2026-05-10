import os
import warnings
import psycopg2
import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine
from geoalchemy2 import Geometry, WKTElement
from shapely import wkt
import shapely.geometry.base
import osmnx as ox
import geojson 
import json
from shapely.geometry import Polygon
from h3 import h3
import psutil
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

class BannerAnimator:
    def __init__(self, json_path):
        self.frames = []
        self.current_frame = 0
        self.fps = 30
        self.load_frames(json_path)

    def load_frames(self, path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                self.fps = data.get('animation', {}).get('frameRate', 30)
                for f in data.get('frames', []):
                    # Join lines with newlines
                    self.frames.append("\n".join(f.get('content', [])))
        except Exception as e:
            print(f"Error loading banner: {e}")
            self.frames = ["+ C I C L O +"]

    def get_next_frame(self):
        if not self.frames: return ""
        frame = self.frames[self.current_frame]
        self.current_frame = (self.current_frame + 1) % len(self.frames)
        return frame

# Metadata Standard Schemas (INE and SECTRA)
CHILEAN_SCHEMAS = {
    "INE_CENSO_2024": {
        "pop_total": ["pop_h3", "PERSONAS", "TOTAL_PERS", "CANT_PERS", "n_per"],
        "age_0_14": ["P01_1", "EDAD_0_14"],
        "age_65_plus": ["P01_3", "EDAD_65_MAS"],
        "households": ["HOGARES", "TOTAL_HOG"],
        "geometry": ["geometry", "geom"]
    },
    "SECTRA_EOD": {
        "trips": ["trips", "VIAJES", "n_viajes"],
        "expansion_factor": ["Factor_Expansion", "FACTOR", "FACTOR_EXPANSION", "factor_exp"],
        "purpose": ["Proposito", "PROPOSITO_VIAJE"],
        "mode": ["Modo", "MODO_TRANSPORTE"],
        "h3_origin": ["h3_origin", "ORIGEN_H3"],
        "h3_dest": ["h3_dest", "h3_destination", "DESTINO_H3"]
    }
}

class DiagnosticHandler:
    '''
    Description: Handles Phase 4 Observability Framework (Errors and Warnings).
    '''
    def __init__(self):
        self.diagnostics = []

    def report(self, code, level, message):
        emoji = "💡" if level == "INFO" else "⚠️" if level == "WARNING" else "🔴"
        color = "cyan" if level == "INFO" else "yellow" if level == "WARNING" else "red"
        self.diagnostics.append({"code": code, "level": level, "message": message, "color": color, "emoji": emoji})
        # Log to rich console with emoji
        console.print(f"{emoji} [{color} BOLD][{level}] {code}:[/] {message}")

    def validate_inputs(self, od_path, census_path, projects_path=None):
        '''Operational: Check existence and basic schema format'''
        results = []
        
        # Check OD Matrix
        if od_path:
            exists = os.path.exists(od_path)
            status = "[green]EXISTS[/]" if exists else "[red]MISSING[/]"
            results.append(["OD Matrix", os.path.basename(od_path), status])
            if exists and od_path.endswith('.csv'):
                try:
                    df_test = pd.read_csv(od_path, nrows=5)
                    required = ['h3_origin', 'h3_dest', 'trips']
                    missing = [col for col in required if col not in df_test.columns]
                    if missing:
                        self.report("INVALID_FORMAT", "ERROR", f"OD Matrix missing: {missing}")
                    else:
                        results.append(["OD Schema", "Columns Validated", "[green]PASSED[/]"])
                except:
                    results.append(["OD Schema", "Read Error", "[red]FAILED[/]"])
        
        # Check Census
        if census_path:
            exists = os.path.exists(census_path)
            status = "[green]EXISTS[/]" if exists else "[red]MISSING[/]"
            results.append(["Census Data", os.path.basename(census_path), status])

        # Check Projects (Phase 5)
        if projects_path:
            exists = os.path.exists(projects_path)
            status = "[green]EXISTS[/]" if exists else "[red]MISSING[/]"
            results.append(["Scenario Projects", os.path.basename(projects_path), status])

        return results

    def get_input_table(self, od_path, census_path, projects_path=None):
        table = Table(title="[bold blue]Pre-flight Input Checklist", box=None, expand=True)
        table.add_column("Resource", style="bold")
        table.add_column("Source/Detail")
        table.add_column("Status", justify="right")
        
        results = self.validate_inputs(od_path, census_path, projects_path)
        for res in results:
            table.add_row(*res)
        return table

    def get_mem_usage(self):
        '''Computational: Memory tracking'''
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # In MB

    def audit_network(self, conn, table_name, components_table):
        '''Scientific: Check for fragmentation and islands'''
        query = f"SELECT count(*) as total, count(*) FILTER (WHERE component != (SELECT component FROM {components_table} GROUP BY component ORDER BY count(*) DESC LIMIT 1)) as isolated FROM {components_table};"
        with conn.cursor() as cursor:
            cursor.execute(query)
            res = cursor.fetchone()
            isolated_pct = (res[1] / res[0]) * 100 if res[0] > 0 else 0
            if isolated_pct > 20:
                self.report("NETWORK_FRAGMENTATION", "WARNING", f"Graph is highly fragmented. {isolated_pct:.1f}% of nodes are isolated islands.")
            else:
                self.report("TOPOLOGY_HEALTH", "INFO", f"Network connected. Isolated nodes: {isolated_pct:.1f}%")

    def metadata_audit(self, source_name, columns):
        '''Operational: Report detected schema mapping'''
        mapping = {}
        schema = CHILEAN_SCHEMAS.get(source_name, {})
        for internal, aliases in schema.items():
            # Match if column is exactly the internal name OR in aliases
            all_aliases = [internal] + aliases
            found = [col for col in columns if col in all_aliases]
            if found:
                mapping[internal] = found[0]
        
        if mapping:
            self.report("METADATA_MAPPING", "INFO", f"Detected {source_name} schema. Mapped {len(mapping)} attributes.")
        return mapping

diagnostic_handler = DiagnosticHandler()

sql_base_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                    'sql-scripts')

#Ignore warning
warnings.filterwarnings('ignore', 'GeoSeries.notna', UserWarning)

def create_conn(database_name, host, port, user, password):
    '''
    Description: This function creates a connection to a postgres database
    Input: database_name, host, port, user, password
    Output: connection object
    '''
    conn = psycopg2.connect(
        dbname=database_name,
        host=host,
        port=port,       
        user=user,
        password=password
    )
    return conn

def read_any_spatial_file(file_path, bbox=None):
    '''
    Description: Robust reader for CSV (H3), GeoJSON, and Parquet with optional BBOX clipping.
    '''
    if file_path.endswith('.parquet'):
        return gpd.read_parquet(file_path, bbox=tuple(bbox) if bbox is not None else None)
    elif file_path.endswith('.csv'):
        return pd.read_csv(file_path)
    else:
        return gpd.read_file(file_path)


def df_to_postgres(df, table_name, geom_type, srid, user, password, host, port, database_name):
    '''
    Description: upload a df object into a database
    Input: df object and a name for the table   
    '''
    # ensure integer
    srid = int(srid)

    # Convert geometry to WKTElement if it exists
    if 'geometry' in df.columns:
        df['geometry'] = df['geometry'].apply(lambda geom: WKTElement(geom, srid=srid))
        dtype = {'geometry': Geometry(geom_type, srid=srid)}
    else:
        dtype = {}

    # Create SQL Alchemy Engine
    engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{database_name}')

    # Write to PostgreSQL
    df.to_sql(
        table_name, 
        engine, 
        if_exists='replace', 
        index=False, 
        dtype=dtype
    )

    if 'geometry' in df.columns:
        #Create spatial Index 
        sql_file_path = os.path.join(sql_base_path, 'create_spatial_index.sql')
        query_template = read_sql_file(sql_file_path)
        query = query_template.format(layer_name=table_name, schema_name='public')
        conn = create_conn(database_name,host,port,user,password)
        execute_query(conn, query)

    print('Table '+table_name+' imported')


def read_sql_file(file_path):
    '''
    Description: read an SQL file and create a string object with the query 
    Input: path of SQL file
    Output: SQL query as a string
    '''
    with open(file_path, 'r') as file:
        sql = file.read()
    return sql

def create_abbreviation(area):
    words = area.split(", ")
    abbreviation = "".join([word[:4].lower() for word in words])
    return abbreviation


def get_bbox_from_data(file_path, srid):
    '''
    Description: Extracts the bounding box (WGS84) from a spatial file or H3-indexed CSV.
    '''
    if file_path.endswith('.geojson') or file_path.endswith('.json'):
        df = gpd.read_file(file_path)
        # Ensure it's in 4326 for OSMNX
        df_4326 = df.to_crs(epsg=4326)
        return df_4326.total_bounds # (west, south, east, north)
    
    elif file_path.endswith('.parquet'):
        # For national Parquet, we peek at the columns to see if we can get a bbox
        # Usually it's better to provide a bbox to the reader, but if we need to find it:
        df = gpd.read_parquet(file_path)
        df_4326 = df.to_crs(epsg=4326)
        return df_4326.total_bounds

    elif file_path.endswith('.csv'):
        # Assume it has H3 indices (h3_origin or h3_index)
        df = pd.read_csv(file_path)
        h3_col = 'h3_origin' if 'h3_origin' in df.columns else 'h3_index'
        if h3_col in df.columns:
            import h3.api.basic_int as h3_int # Using basic for speed if needed, but h3.h3 is fine
            coords = [h3.h3_to_geo(h) for h in df[h3_col].unique()]
            lats, lons = zip(*coords)
            return min(lons), min(lats), max(lons), max(lats)
    
    return None

def download_osm(area, srid, type_network, bbox=None):
    # Download data from OSM
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
        # Filter Point geometries
        features = nodes[nodes['highway'].isin(usable)]
    else:
        # Filter LineStrings
        lines = edges[edges['geometry'].geom_type == 'LineString']

        # Filter selected highways
        if type_network == 'osm':
            usable = ['residential', 'primary', 'secondary', 'tertiary']
        elif type_network == 'bike':
            usable = ['cycleway']
        else:
            usable = ['primary', 'secondary', 'tertiary']

        features = lines[lines['highway'].isin(usable)]
        
    # Reproject to the specified SRID
    features = features.to_crs(epsg=srid)

    # --- Data Integrity Guard (#TS31) ---
    if len(features) == 0:
        raise ValueError(f"CRITICAL ERROR: No segments found for {type_network} in this area. Check internet connection or BBOX constraints.")

    # Return the result
    return features

def extract_h3_grid_from_od(od_file_path, table_name, srid, user, password, host, port, database_name):
    '''
    Description: Reads unique H3 indices from OD matrix and creates a geometry table in PostGIS.
    '''
    df_od = pd.read_csv(od_file_path)
    
    # Get all unique H3 indices (origins and destinations)
    h3_o = set(df_od['h3_origin'].unique())
    h3_d = set(df_od['h3_dest'].unique())
    unique_h3 = h3_o.union(h3_d)
    
    count = len(unique_h3)
    
    # Generate geometries
    geometry = [Polygon(h3.h3_to_geo_boundary(h, geo_json=True)) for h in unique_h3]
    
    h3_gdf = gpd.GeoDataFrame({
        'h3_index': list(unique_h3),
        'geometry': geometry
    }, crs="EPSG:4326")
    
    # Transform to metric CRS
    h3_gdf = h3_gdf.to_crs(epsg=srid)
    
    # Upload to PostGIS
    engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{database_name}')
    h3_gdf.to_postgis(name=table_name+'_h3', con=engine, if_exists='replace')
    return count

def download_h3(table, srid, res, user, password, host, port, database_name):
    engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{database_name}')
    sql = f'SELECT geometry as geom from {table}'
    df = gpd.read_postgis(sql,engine)

    # Set srid
    df = df.to_crs(epsg=srid)

    print(f"Number of df record: {len(df)}")

    # Convert to EPSG:4326 for H3
    df_4326 = df.to_crs(epsg=4326)

    # Get bbox
    west, south, east, north = df_4326.total_bounds

    polygon_geojson = geojson.Feature(geometry=Polygon([(west, south), (east, south), (east, north), (west, north)]), properties={})

    # Create dict
    polygon_dict = json.loads(geojson.dumps(polygon_geojson.geometry))

    # Obtain the H3 hexagons for the area
    h3_hexagons = h3.polyfill(polygon_dict, res=int(res), geo_json_conformant=True)
    print(f"Number of H3 hexagons generated: {len(h3_hexagons)}")

    # Create the geometry column
    geometry = [Polygon(h3.h3_to_geo_boundary(h, geo_json=True)) for h in h3_hexagons]

    # Convert to GeoDataFrame with H3 indices
    h3_hexagons_gdf = gpd.GeoDataFrame({
        'h3_index': list(h3_hexagons),
        'geometry': geometry
    })

    # Set the CRS for the GeoDataFrame
    h3_hexagons_gdf.crs = "EPSG:4326"  # H3 works with EPSG:4326
    
    # Convert back to original CRS for storage
    h3_hexagons_gdf = h3_hexagons_gdf.to_crs(epsg=srid)

    try:
        h3_hexagons_gdf.to_postgis(name=table+'_h3', con=engine, if_exists='replace')
        print('H3 data successfully written to PostGIS.')
    except Exception as e:
        print('An error occurred while writing H3 data to PostGIS:')
        print(e) #exception


def create_filters_string(arg_proye, arg_ci_o_cr, arg_op_ci):
    filters = []
    
    if arg_proye == 0:
        filters.append('proyect = 0') 
    if arg_ci_o_cr == 0:
        filters.append('"CI_O_CR" = 0')
    if arg_op_ci == 0:
        filters.append('op_ci = 0')

    if not filters:
        return None

    filters_string = " AND ".join(filters)

    return filters_string

def create_suffix_string(arg_proye, arg_ci_o_cr, arg_op_ci):
    filters = []
    
    if arg_proye == 0:
        filters.append('proye_0') 
    if arg_ci_o_cr == 0:
        filters.append('ci_o_cr_0')
    if arg_op_ci == 0:
        filters.append('op_ci_0')

    if not filters:
        return ''

    filters_string = "_".join(filters)
    filters_string = '_'+filters_string
    return filters_string

def execute_query(conn, query):
    '''
    Description: Executes a query on a connection with given parameters
    Input: conn - connection object, query - SQL query string, params - tuple of parameters
    '''
    with conn.cursor() as cursor:
        cursor.execute(query)
        conn.commit()

def upload_csv_to_db(file_path, table_name, user, password, host, port, database_name):
    '''
    Description: Uploads a standard CSV to PostgreSQL using Pandas
    '''
    df = pd.read_csv(file_path)
    engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{database_name}')
    df.to_sql(table_name, engine, if_exists='replace', index=False)
    print(f'Table {table_name} uploaded from CSV.')


def check_table_existence(conn, table_name):
    '''
    Description: This function checks if a table exists in the connected database
    Input: conn - connection object, table_name - string
    Output: Boolean value indicating if the table exists
    '''
    query = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE  table_name   = %s
        );
    """
    with conn.cursor() as cursor:
        cursor.execute(query, (table_name,))
        return cursor.fetchone()[0]

def handle_path_argument(type_network, path_arg, base_file_path, table_name, location_input, geom_type, srid, user, password, host, port, database_name, bbox=None):
    '''
    Input: bbox - optional bounding box for spatial anchoring and RAM optimization
    '''
    conn = create_conn(database_name, host, port, user, password)

    if path_arg is None or path_arg == 'None':
        print(f'Skipping {type_network} as no input was provided.')
        return

    if path_arg == '':
        # if exist then skipp, else upload base file example
        if check_table_existence(conn, table_name):
            print(f'Table {table_name} already exists, skipping import.')
        else:
            df_osm = read_any_spatial_file(base_file_path)
            df_to_postgres(df_osm, table_name, geom_type, srid=srid,
                            user=user, password=password, host=host, 
                            port=port, database_name=database_name)
            print(f'Table {table_name} is loaded into database')

    elif path_arg == 'osm':
        print(f'Processing {type_network} using OSM source')
        df_osm = download_osm(location_input, srid, type_network, bbox=bbox)
        print(f'uploading to db as {table_name}')
        df_to_postgres(df_osm, table_name, geom_type, srid=srid,
                        user=user, password=password, host=host, 
                        port=port, database_name=database_name)
        print(f'{table_name} uploaded')

    else:  # path_arg is a string path
        print(f"Reading file located at {path_arg}")
        df = read_any_spatial_file(path_arg, bbox=bbox)
        
        # Metadata Audit
        # Map type_network to internal schema keys
        type_to_schema = {
            'census': 'INE_CENSO_2024',
            'od': 'SECTRA_EOD'
        }
        source_type = type_to_schema.get(type_network)
        
        mapping = {}
        if source_type:
            mapping = diagnostic_handler.metadata_audit(source_type, df.columns.tolist())
        
        # If we have a mapping, we can rename columns to standard names for the DB
        if mapping:
            # Trip Scaling Logic: if both trips and expansion_factor exist, multiply them
            if 'trips' in mapping and 'expansion_factor' in mapping:
                t_col = mapping['trips']
                e_col = mapping['expansion_factor']
                df[t_col] = df[t_col] * df[e_col]
                diagnostic_handler.report("DEMAND_SCALING", "INFO", f"Scaled {t_col} by {e_col}.")

            # We only rename columns that were explicitly mapped
            rename_dict = {v: k for k, v in mapping.items()}
            df = df.rename(columns=rename_dict)
            print(f"Mapped {len(mapping)} columns for {source_type}")

        print(f'uploading from path argument to db as {table_name}')
        
        # If it's bike/osm and not LineString, explode it
        if 'geometry' in df.columns and geom_type == 'LineString':
            # Check if we need to explode
            types = df.geometry.type.unique()
            if 'MultiLineString' in types:
                df = df.explode(index_parts=True)

        df_to_postgres(df, table_name, geom_type, srid=srid,
                        user=user, password=password, host=host, 
                        port=port, database_name=database_name)
