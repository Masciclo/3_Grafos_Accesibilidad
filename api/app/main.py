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
parser.add_argument("--inhibidores", dest="inhib", required=True, type=int, help="inhibir o no la red")
parser.add_argument("--desinhibidores", dest="desinhib", required=True, type=int, help="desinhibir o no la red")
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


def data_pipeline(ciclo_file_path, osm_file_path, inhibitor, desinhibitor, location):
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


    # Read CSV to DataFrame
    df_osm = utils.read_csv_to_df(ciclo_file_path_)
    df_ciclos = utils.read_csv_to_df(osm_file_path_)

    # Create name of tables in db
    osm_table_name = f'{location}_osm'
    ciclos_table_name = f'{location}_ciclos'

    # Insert DataFrame into PostgreSQL
    utils.df_to_postgres(df_osm, 
                        osm_table_name,
                        USER,
                        PASSWORD,
                        HOST,
                        PORT,
                        DATABASE_NAME)

    utils.df_to_postgres(df_ciclos, 
                        ciclos_table_name,
                        USER,
                        PASSWORD,
                        HOST,
                        PORT,
                        DATABASE_NAME)

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
    params = ()
    utils.execute_query_with_params(conn, query, params)

    # Use Inhibitor or not
    if inhibitor:
        # Define path to sql query and table names
        sql_file_path_inhib = os.path.join(sql_base_path,
                                'create_buffer.sql')
        inhibitor_input_name = f'{location}_inhib'
        inhibitor_result_name = f'{location}_network_inhib'
        query_template_inhib = utils.read_sql_file(sql_file_path_inhib)
        # Format sql query
        query = query_template_inhib.format(result_name=inhibitor_result_name, 
                                  inhibitor_table_name=inhibitor_input_name, 
                                  metros=osm_table_name
                                  # agregar todos los,
                                  # parametros de query
                                  ) 
                                  
        # Execute query formated
        utils.execute_query_with_params(conn, query, params)
    else:
        print('inhibitors are not processing')


    # Use desinhibitor or not depend on the inhibitor step
    if desinhibitor==True & inhibitor == True:
        desinhibitor_input_name = inhibitor_result_name
        desinhibitor_result_name = f'{location}_network_inhib_desinhib'
    elif desinhibitor==True & inhibitor == False:
        desinhibitor_input_name = sql_file_path
        desinhibitor_result_name = f'{location}_network_desinhib'
    elif desinhibitor==False & inhibitor == True:
        desinhibitor_result_name = f'{location}_network_inhib'
    else:
        pass

    if desinhibitor:    
        # Define path to sql query and table names
        sql_file_path_desinhib = os.path.join(sql_base_path,
                                'create_buffer.sql')
        
        query_template_inhib = utils.read_sql_file(sql_file_path_desinhib)
        # Format sql query
        query = query_template_inhib.format(buffer_name=desinhibitor_result_name, 
                                    network_input=desinhibitor_input_name,
                                    # add more parameters
                                    )
        # Execute query formated
        utils.execute_query_with_params(conn, query, params)
    else:
        print('desinhibitor are not processing')


    # Final difference
    
    # delete_line_segments_in_polygon

    # create_clean_topology

    # calculate things


def main():
    sys.setrecursionlimit(1500)
    args = parser.parse_args()
    data_pipeline(args.ciclos_path, args.osm_path, args.inhib, args.desinhib, args.location)

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