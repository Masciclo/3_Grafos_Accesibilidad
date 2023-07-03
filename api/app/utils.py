import os
import warnings
import psycopg2
import geopandas as gpd
from sqlalchemy import create_engine
from geoalchemy2 import Geometry, WKTElement
from shapely import wkt
import shapely.geometry.base
import osmnx as ox

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


def download_osm(area, srid, type_network):
    # Download data from OSM
    graph = ox.graph_from_place(area, network_type='all')
    edges = ox.graph_to_gdfs(graph, nodes=False, edges=True)
    nodes = ox.graph_to_gdfs(graph, nodes=True, edges=False)  # new line: get the nodes
    
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
        elif type_network == 'ciclo':
            usable = ['bike']
        else:
            usable = ['primary', 'secondary', 'tertiary']

        features = lines[lines['highway'].isin(usable)]
        
    # Reproject to the specified SRID
    features = features.to_crs(epsg=srid)

    # Return the result
    return features



def create_filters_string(arg_proye, arg_ci_o_cr, arg_op_ci):
    filters = []
    
    if arg_proye == 0:
        filters.append('proye = 0') 
    if arg_ci_o_cr == 0:
        filters.append('ci_o_cr = 0')
    if arg_op_ci == 0:
        filters.append('op_ci = 0')

    if not filters:
        return None

    filters_string = " AND ".join(filters)

    return filters_string


def execute_query(conn, query):
    '''
    Description: Executes a query on a connection with given parameters
    Input: conn - connection object, query - SQL query string, params - tuple of parameters
    '''
    with conn.cursor() as cursor:
        cursor.execute(query)
        conn.commit()


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
def handle_path_argument(type_network, path_arg, base_file_path, table_name, location_input, geom_type, srid, user, password, host, port, database_name):
    '''
    Description: This function handles path input argument in three different ways based on its value
    Input: path_arg - input argument which can be None, 'osm', or 'string_path'
           location - the location used to form the table name
           osm_file_path - the path of the base osm file
           conn - database connection
           table_name - the name of the table in the database
           geom_type - the geometry type of the spatial data
           user, password, host, port, database_name - database credentials
    Output: None, but has side effects like creating a table in the database
    '''

    conn = create_conn(database_name,host,port,user,password)

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
        df_osm = download_osm(location_input, srid, type_network)
        df_to_postgres(df_osm, table_name, geom_type, srid=srid,
                        user=user, password=password, host=host, 
                        port=port, database_name=database_name)
        print(f'downloading from osm and uploading to db as {table_name}')

    else:  # path_arg is a string path
        df_osm = read_csv_to_df(path_arg)
        print('uploading from path argument to db')
        df_to_postgres(df_osm, table_name, geom_type, srid=srid,
                        user=user, password=password, host=host, 
                        port=port, database_name=database_name)