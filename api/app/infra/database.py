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

import subprocess

def stream_file_to_postgres(file_path, table_name, srid, user, password, host, port, database_name):
    """
    Description: Uses ogr2ogr to stream large spatial files directly to PostGIS.
    This is significantly faster and more memory-efficient than GeoPandas for metropolitan datasets.
    """
    cmd = [
        "ogr2ogr",
        "-f", "PostgreSQL",
        f"PG:dbname={database_name} host={host} port={port} user={user} password={password}",
        file_path,
        "-nln", table_name,
        "-overwrite",
        "-t_srs", f"EPSG:{srid}",
        "-lco", "GEOMETRY_NAME=geometry",
        "-lco", "FID=id",
        "-nlt", "PROMOTE_TO_MULTI"
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        # Post-injection index
        conn = create_conn(database_name, host, port, user, password)
        execute_query(conn, f"CREATE INDEX IF NOT EXISTS {table_name}_geom_idx ON {table_name} USING GIST (geometry);")
        print(f"Table {table_name} streamed successfully via ogr2ogr.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Ogr2ogr failed: {e.stderr.decode()}")
        return False

def df_to_postgres(df, table_name, geom_type, srid, user, password, host, port, database_name, mode='replace'):
    '''
    Description: upload a df object into a database with atomicity and spatial indexing.
    Optimized for Metropolitan scale (Pre-conversion chunking).
    '''
    if srid is not None:
        srid = int(srid)
    
    engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{database_name}')
    
    # --- Strategy: ID Enforcement ---
    # Ensure we have a simple integer ID column for pgRouting
    df = df.copy()
    if 'id' not in df.columns:
        df = df.reset_index()
        if 'index' in df.columns:
            df = df.rename(columns={'index': 'id'})
        else:
            # Handle multi-index or other index types
            df['id'] = range(1, len(df) + 1)
    
    # --- Strategy: Pre-conversion Chunking ---
    chunk_size = 5000
    chunks = [df[i:i + chunk_size] for i in range(0, df.shape[0], chunk_size)]
    
    with engine.begin() as connection:
        for i, df_chunk in enumerate(chunks):
            current_mode = 'replace' if (i == 0 and mode == 'replace') else 'append'
            
            # --- Safety: Drop null geometries ---
            if 'geometry' in df_chunk.columns:
                df_chunk = df_chunk[df_chunk['geometry'].notnull()].copy()

            # Convert geometry to WKTElement for THIS CHUNK ONLY
            if 'geometry' in df_chunk.columns:
                df_chunk['geometry'] = df_chunk['geometry'].apply(lambda geom: WKTElement(geom, srid=srid))
                dtype = {'geometry': Geometry(geom_type, srid=srid)}
            else:
                dtype = {}

            # Write chunk to PostgreSQL
            df_chunk.to_sql(
                table_name, 
                connection, 
                if_exists=current_mode, 
                index=False, 
                dtype=dtype,
                method=None
            )

            if 'geometry' in df_chunk.columns and current_mode == 'replace':
                # Create spatial Index only on the first chunk
                sql_file_path = os.path.join(sql_base_path, 'create_spatial_index.sql')
                with open(sql_file_path, 'r') as f:
                    query_template = f.read()
                query = query_template.format(layer_name=table_name, schema_name='public')
                connection.execute(text(query))
    
    print(f'Table {table_name} imported successfully ({len(chunks)} chunks).')

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
