import psycopg2
from sqlalchemy import create_engine, text
from geoalchemy2 import Geometry, WKTElement
import os

# Base path for internal SQL templates
sql_base_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'sql', 'common')

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

def execute_query(conn, query):
    '''
    Description: Executes a query on a connection with given parameters
    Input: conn - connection object, query - SQL query string
    '''
    with conn.cursor() as cursor:
        cursor.execute(query)
        conn.commit()

def df_to_postgres(df, table_name, geom_type, srid, user, password, host, port, database_name):
    '''
    Description: upload a df object into a database with atomicity and spatial indexing.
    '''
    srid = int(srid)

    # --- Safety: Drop null geometries (#Issue 05) ---
    if 'geometry' in df.columns:
        df = df[df['geometry'].notnull()]

    # Convert geometry to WKTElement if it exists
    if 'geometry' in df.columns:
        df['geometry'] = df['geometry'].apply(lambda geom: WKTElement(geom, srid=srid))
        dtype = {'geometry': Geometry(geom_type, srid=srid)}
    else:
        dtype = {}

    # Create SQL Alchemy Engine
    engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{database_name}')

    # Write to PostgreSQL with connection management
    with engine.connect() as connection:
        df.to_sql(
            table_name, 
            connection, 
            if_exists='replace', 
            index=False, 
            dtype=dtype
        )

        if 'geometry' in df.columns:
            # Create spatial Index using late-binding template
            sql_file_path = os.path.join(sql_base_path, 'create_spatial_index.sql')
            with open(sql_file_path, 'r') as f:
                query_template = f.read()
            query = query_template.format(layer_name=table_name, schema_name='public')
            connection.execute(text(query))
    
    print(f'Table {table_name} imported successfully.')

def check_table_existence(conn, table_name):
    '''
    Description: Checks if a table exists in the connected database
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

def read_sql_file(file_path):
    '''
    Description: read an SQL file and create a string object with the query 
    '''
    with open(file_path, 'r') as file:
        sql = file.read()
    return sql

def upload_csv_to_db(file_path, table_name, user, password, host, port, database_name):
    import pandas as pd
    df = pd.read_csv(file_path)
    engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{database_name}')
    df.to_sql(table_name, engine, if_exists='replace', index=False)
    print(f'Table {table_name} uploaded from CSV.')
