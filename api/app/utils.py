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

    def validate_inputs(self, od_path, census_path):
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

        return results

    def get_input_table(self, od_path, census_path):
        table = Table(title="[bold blue]Pre-flight Input Checklist", box=None, expand=True)
        table.add_column("Resource", style="bold")
        table.add_column("Source/Detail")
        table.add_column("Status", justify="right")
        
        results = self.validate_inputs(od_path, census_path)
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

def read_csv_to_df(file_path):
    '''
    Description: This function reads a csv file into a GeoPandas DataFrame
    Input: path of csv file
    Output: DataFrame
    '''

    df = gpd.read_file(file_path) # Read file
    return df


def df_to_postgres(df, table_name,geom_type, srid, user, password, host, port, database_name):
    '''
    Description: upload a df object into a database
    Input: df object (from read_csv_to_df function) and a name for the table   
    '''
    # ensure integer
    srid = int(srid)

    # Convert geometry to WKTElement
    df['geometry'] = df['geometry'].apply(lambda geom: WKTElement(geom, srid=srid))

    # Create SQL Alchemy Engine
    engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{database_name}')

    # Write to PostgreSQL
    df.to_sql(
        table_name, 
        engine, 
        if_exists='replace', 
        index=False, 
        dtype={'geometry': Geometry(geom_type, srid=srid)}
    )

    #Create spatial Index 
    sql_file_path = os.path.join(sql_base_path,
                                'create_spatial_index.sql')
    query_template = read_sql_file(sql_file_path)
    query = query_template.format(layer_name=table_name, 
                                schema_name='public')
    # create connection
    conn = create_conn(database_name,host,port,user,password)
    # execute query
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

##Revisar location
def handle_path_argument(type_network, path_arg, base_file_path, table_name, location_input, geom_type, srid, user, password, host, port, database_name, bbox=None):
    '''
    Description: This function handles path input argument in three different ways based on its value
    Input: path_arg - input argument which can be None, 'osm', or 'string_path'
           location - the location used to form the table name
           osm_file_path - the path of the base osm file
           conn - database connection
           table_name - the name of the table in the database
           geom_type - the geometry type of the spatial data
           user, password, host, port, database_name - database credentials
           bbox - optional bounding box for spatial anchoring
    Output: None, but has side effects like creating a table in the database
    '''

    conn = create_conn(database_name,host,port,user,password)

    if path_arg is None or path_arg == 'None':
        print(f'Skipping {type_network} as no input was provided.')
        return

    if path_arg == '':
        # if exist then skipp, else upload base file example
        if check_table_existence(conn, table_name):
            print(f'Table {table_name} already exists, skipping import.')
        else:
            df_osm = read_csv_to_df(base_file_path)
            df_to_postgres(df_osm, table_name, geom_type, srid=srid,
                            user=user, password=password, host=host, 
                            port=port, database_name=database_name)
            print(f'Table {table_name} is loaded into database')

    
    elif path_arg == 'osm':
        # download_osm function should return the path to the downloaded file
        print(f'Processing {type_network} using OSM source')
        df_osm = download_osm(location_input, srid, type_network, bbox=bbox)
        print(f'uploading to db as {table_name}')
        df_to_postgres(df_osm, table_name, geom_type, srid=srid,
                        user=user, password=password, host=host, 
                        port=port, database_name=database_name)
        print(f'{table_name} uploaded')
        

    else:  # path_arg is a string path
        print(f"Leyendo archivo ubicado en {path_arg}")
        df_osm = read_csv_to_df(path_arg)
        print(f'uploading from path argument to db')
        if df_osm.geometry.type[0] == "Linestring":    
            df_to_postgres(df_osm, table_name, geom_type, srid=srid,
                            user=user, password=password, host=host, 
                            port=port, database_name=database_name)
        else:
            df_osm = df_osm.explode()
            df_to_postgres(df_osm, table_name, geom_type, srid=srid,
                user=user, password=password, host=host, 
                port=port, database_name=database_name)
