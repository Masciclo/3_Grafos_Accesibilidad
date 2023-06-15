#Python main script to procces GIS data and obtain 
# several bike-path-oriented metrics of a given topology 

#TODO: create connection, read the queries, analize parameters to use, 
# put paremeters in sql and create pipeline with exceptions.


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
parser.add_argument("--ciclos_path", dest="ciclos_path", required=True, type=str, help="ciclos network path")
parser.add_argument("--osm_path", dest="osm_path", required=True, type=str, help="osm network path")
parser.add_argument("--location", dest="location", required=True, type=str, help="location to process")


#load env variables
load_dotenv()

#define variables of
DATABASE_NAME = os.getenv('URL_ENGINE')
HOST = os.getenv('HOST')
PORT = os.getenv('PORT')
USER = os.getenv('USER')
PASSWORD = os.getenv('PASSWORD')



def data_pipeline(ciclo_network_path, osm_network_path, inhibitor, desinhibitor, location):
    '''
    - Description: Execute the functions in order to get the result 
    - Input: path of csv file, postgres table name of result table, 
    list of queries (str).
    '''
    
    # Read CSV to DataFrame
    df_network = utils.read_csv_to_df(ciclo_network_path)
    df_ciclos = utils.read_csv_to_df(osm_network_path)

    network_table_name = f'{location}_network'
    ciclos_table_name = f'{location}_ciclos'

    # Insert DataFrame into PostgreSQL
    utils.df_to_postgres(df_network, 
                        network_table_name)
    utils.df_to_postgres(df_ciclos, 
                        ciclos_table_name)

    # Merge ciclo and vial network
    full_network_name = f'{location}_full_network'
    
    # Read SQL file and format query string
    sql_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                    '..',
                    '..', 
                    'db',
                    'sql-scripts',
                    'create_full_network.sql')
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(result_name=full_network_name, 
                                  ciclo=ciclos_table_name, 
                                  osm=network_table_name)

    # Connect to PostgreSQL
    conn = utils.create_conn(DATABASE_NAME,HOST,PORT,USER,PASSWORD)

    # Execute query
    params = ()
    utils.execute_query_with_params(conn, query, params)

def main():
    sys.setrecursionlimit(1500)
    args = parser.parse_args()
    data_pipeline(args.osm_path, args.ciclos_path, args.inhib, args.desinhib, args.location)

if __name__=='__main__':
    main()
    #python3 main.py --inhibidores=0 --desinhibidores=1 --ciclos_path='../../db/data/' --osm_path=str --location=str





# Example usage
#data_pipeline('my_data.csv', 'my_table', ['SQL QUERY 1', 'SQL QUERY 2'])




# Connect to PostgreSQL
#conn = utils.create_conn(DATABASE_NAME,HOST,PORT,USER,PASSWORD)



#query_list = ['create_full_network.sql','','','','','']

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