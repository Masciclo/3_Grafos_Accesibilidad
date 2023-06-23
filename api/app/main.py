#Python main script to procces GIS data and obtain 
# several bike-path-oriented metrics of a given topology 


import pandas as pd
import geopandas as gpd
from dotenv import load_dotenv
import os
import argparse
import sys
import utils


parser = argparse.ArgumentParser(description='Run necessary queries to create the tables with results in postgreSQL')
parser.add_argument("--inhibidores", dest="inhib", required=False, type=str, help="inhibir o no la red")
parser.add_argument("--buffer_inhibidores", dest="buffer_inhib", required=False, type=float, help="metros de buffer aplicado a los inhibidores")
parser.add_argument("--desinhibidores", dest="desinhib", required=False, type=str, help="desinhibir o no la red")
parser.add_argument("--buffer_desinhibidores", dest="buffer_desinhib", required=False, type=float, help="metros de buffer aplicado a los desinhibidores")
parser.add_argument("--ciclos_path", dest="ciclos_path", required=False, type=str, help="ciclos network path")
parser.add_argument("--osm_path", dest="osm_path", required=False, type=str, help="osm network path")
parser.add_argument("--location", dest="location", required=True, type=str, help="location to process")


#load env variables
load_dotenv()

#define variables of
DATABASE_NAME = os.getenv('DATABASE_NAME')
HOST = os.getenv('HOST')
PORT = os.getenv('PORT')
USER = os.getenv('USER')
PASSWORD = os.getenv('PASSWORD')


sql_base_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                    'sql-scripts')

data_base_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                    'data')


def data_pipeline(ciclo_file_path, osm_file_path, inhibitor_file_path, buffer_inhib, desinhibitor_file_path, buffer_desinhib, location):
    '''
    - Description: Execute the functions in order to get the result 
    - Input: path of csv file, postgres table name of result table, 
    list of queries (str).
    '''
    
    # In case of None value for arguments path files
    if ciclo_file_path is None:
        ciclo_file_path_ = os.path.join(data_base_path,
                                          'calidad_cliped.geojson')
    else:
        ciclo_file_path_= ciclo_file_path
    if osm_file_path is None:
        osm_file_path_ = os.path.join(data_base_path,
                                          'ejes_osm_cliped.geojson')
    else:
        osm_file_path_ = osm_file_path
    if inhibitor_file_path is None:
        inhibitor_file_path_ = os.path.join(data_base_path,
                                 'highways.geojson')
    else:
        inhibitor_file_path_ = inhibitor_file_path
    if desinhibitor_file_path is None:
        desinhibitor_file_path_ = os.path.join(data_base_path,
                                 'semaforos.geojson')
    else:
        desinhibitor_file_path_ = desinhibitor_file_path

    # Read CSV to DataFrame
    df_osm = utils.read_csv_to_df(osm_file_path_)
    df_ciclos = utils.read_csv_to_df(ciclo_file_path_)
    df_inhibitor = utils.read_csv_to_df(inhibitor_file_path_)
    df_desinhibitor = utils.read_csv_to_df(desinhibitor_file_path_)

    # Create name of tables in db
    osm_table_name = f'{location}_osm'
    ciclos_table_name = f'{location}_ciclos'
    inhibitor_table_name = f'{location}_inhibitor'
    desinhibitor_table_name = f'{location}_desinhibitor'

    # Insert OSM DataFrame into PostgreSQL
    utils.df_to_postgres(df_osm, 
                        osm_table_name,
                        'MULTILINESTRING',
                        USER,
                        PASSWORD,
                        HOST,
                        PORT,
                        DATABASE_NAME)

    #Create spatial Index 
    sql_file_path = os.path.join(sql_base_path,
                                'create_spatial_index.sql')
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(layer_name=osm_table_name, 
                                  schema_name='public')
    
    # Insert ciclos DataFrame into PostgreSQL
    utils.df_to_postgres(df_ciclos, 
                        ciclos_table_name,
                        'MULTILINESTRING',
                        USER,
                        PASSWORD,
                        HOST,
                        PORT,
                        DATABASE_NAME)
    
    #Create spatial Index
    sql_file_path = os.path.join(sql_base_path,
                                'create_spatial_index.sql')
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(layer_name=ciclos_table_name, 
                                  schema_name='public')

    # Insert inhibitor DataFrame into PostgreSQL
    utils.df_to_postgres(df_inhibitor,
                         inhibitor_table_name,
                         'MULTILINESTRING',
                         USER,
                         PASSWORD,
                         HOST,
                         PORT,
                         DATABASE_NAME)
    
    sql_file_path = os.path.join(sql_base_path,
                                'create_spatial_index.sql')
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(layer_name=inhibitor_table_name, 
                                  schema_name='public')
    
    # Insert desinhibitor DataFrame into PostgreSQL
    utils.df_to_postgres(df_desinhibitor,
                         desinhibitor_table_name,
                         'MULTILINESTRING',
                         USER,
                         PASSWORD,
                         HOST,
                         PORT,
                         DATABASE_NAME)
    
    sql_file_path = os.path.join(sql_base_path,
                                'create_spatial_index.sql')
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(layer_name=desinhibitor_table_name, 
                                  schema_name='public')

    
    # Merge ciclo and vial network
    full_network_name = f'{location}_full_network'
    
    # Read SQL file and format query string
    sql_file_path = os.path.join(sql_base_path,
                                'create_full_network.sql')

    # Read template query and add parameters                                
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(result_name=full_network_name, 
                                  ciclo=ciclos_table_name, 
                                  osm=osm_table_name)

    # Connect to PostgreSQL
    conn = utils.create_conn(DATABASE_NAME,HOST,PORT,USER,PASSWORD)

    # Execute query to create full network
    print('Creating intermodal network')
    params = ()
    utils.execute_query_with_params(conn, query, params)
    
    # Create Spatial index for the full network
    sql_file_path = os.path.join(sql_base_path,
                                'create_spatial_index.sql')
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(layer_name=full_network_name, 
                                  schema_name='public')

    # Use Inhibitor or not
    if inhibitor_file_path:
        # Define path to sql query and table names
        sql_file_path_buffer = os.path.join(sql_base_path,
                                'create_buffer.sql')
        inhibitor_input_name = inhibitor_table_name
        inhibitor_result_name = f'{location}_network_inhib'+f'_{buffer_inhib}'
        query_template_buffer = utils.read_sql_file(sql_file_path_buffer)
        # Format sql query
        query = query_template_buffer.format(result_name=inhibitor_result_name, 
                                  table_name=inhibitor_input_name, 
                                  metros=buffer_inhib
                                  ) 
                                  
        # Execute query formated
        print('Creating inhibitor buffer')
        utils.execute_query_with_params(conn, query, params)
        # Use Desinhibitor or not
        if desinhibitor_file_path:
            sql_file_path_buffer = os.path.join(sql_base_path,
                                'create_buffer.sql')
            desinhibitor_input_name = desinhibitor_table_name
            desinhibitor_result_name = f'{location}_network_desinhib'+f'_{buffer_inhib}'
            query_template_buffer = utils.read_sql_file(sql_file_path_buffer)
            # Format sql query
            query = query_template_buffer.format(result_name=desinhibitor_result_name, 
                                      table_name=desinhibitor_input_name, 
                                      metros=buffer_desinhib
                                      ) 

            # Execute query formated
            print('Creating desinhibitor buffer')
            utils.execute_query_with_params(conn, query, params)

            # Creating final buffer
            sql_file_path_final_buffer = os.path.join(sql_base_path,
                                'buffer_difference.sql')
            buffer_final_input_name = f'{location}_final_buffer'
            query_template_final_buffer = utils.read_sql_file(sql_file_path_final_buffer)
            # Format sql query
            query = query_template_final_buffer.format(result_name=buffer_final_input_name, 
                                      buffer_inhibitor=inhibitor_result_name, 
                                      buffer_desinhibitor=desinhibitor_result_name
                                      ) 

            # Execute query formated
            print('Calculating buffer difference')
            utils.execute_query_with_params(conn, query, params)

            # delete_line_segments_in_polygon
            sql_file_path_inhibit_network = os.path.join(sql_base_path,
                                        'create_inhibited_network.sql')
            scenery_name = f'{location}_inhibited'
            query_template_inhibit_network = utils.read_sql_file(sql_file_path_inhibit_network)
            # Format sql query
            query = query_template_inhibit_network.format(result_name=scenery_name, 
                                      network_name=full_network_name, 
                                      buffer_name=buffer_final_input_name
                                      )
            # Execute query formated
            print('Inhibiting the network')
            utils.execute_query_with_params(conn, query, params)

        else:
            print('desinhibitor are not processing')

            sql_file_path_inhibit_network = os.path.join(sql_base_path,
                                        'create_inhibited_network.sql')
            scenery_name = f'{location}_inhibited'
            query_template_inhibit_network = utils.read_sql_file(sql_file_path_inhibit_network)
            # Format sql query
            query = query_template_inhibit_network.format(result_name=scenery_name, 
                                      network_name=full_network_name, 
                                      buffer_name=inhibitor_result_name
                                      )
            # Execute query formated
            print('Inhibiting the network')
            utils.execute_query_with_params(conn, query, params)

    else:
        print('Not inhibition applied')

    # Create and clean the topology
    topology_table_name = scenery_name+'_topo'
    # Read SQL file and format query string
    sql_file_path = os.path.join(sql_base_path,
                                'create_clean_topology.sql')

    # Read template query and add parameters                                
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(topo=topology_table_name,
                                  srid=32719,
                                  table=scenery_name)
    print('Generando Topología')                      
    params = ()
    utils.execute_query_with_params(conn, query, params)

    # Calculate Components
    sql_file_path = os.path.join(sql_base_path,
                                'calculate_components.sql')

    # Read template query and add parameters
    components_table_name = full_network_name+'_components'                           
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(topo=topology_table_name,
                                  table_name=full_network_name)
    print('Calculando componentes')                      
    params = ()
    utils.execute_query_with_params(conn, query, params)

    # Calculate Betweenness centrality

    # Calculate Closeness

    # stgo_inhib_0_desinhib_0_
    # stgo_inhib_15_desinhib_25_proye_0)
    


def main():
    sys.setrecursionlimit(1500)
    args = parser.parse_args()
    data_pipeline(args.ciclos_path, args.osm_path, args.inhib, args.buffer_inhib, args.desinhib, args.buffer_desinhib, args.location)

if __name__=='__main__':
    main()

# create extension
# Import ciclo
#Import osm
# spatial index
#full_network = create_full_network.sql
#If inhibidores
    #Import inhibidores
    #bf_inhibidores = create_buffer(inhibidores)
    #If desinhibidores
        #Import desinhibidores
        #bf_desinhibidores = create_buffer(desinhibidores)
    #bf_final = buffer_difference(buffer_inhibidores,buffer_desinhibidores)
    #final_network = delete_line_segments_in_polygon(full_network,bf_final)  
#create_clean_topology(final_network)

# Execute SQL queries
#for query in queries:
#    utils.execute_query_with_params(conn, query