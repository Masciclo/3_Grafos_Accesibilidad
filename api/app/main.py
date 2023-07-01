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
parser.add_argument("--osm_input", dest="osm_input", required=False, type=str, help="osm network path")
parser.add_argument("--ciclo_input", dest="ciclo_input", required=False, type=str, help="ciclos network path")
parser.add_argument("--location", dest="location", required=True, type=str, help="location to process")
parser.add_argument("--srid", dest="srid", required=False, type=str, help="SRID to use for calculate distance/metrics")

parser.add_argument("--inhibit", dest="inhibit", required=True, type=int, help="inhibir o no la red")
parser.add_argument("--inhibitor_input", dest="inhibitor_input", required=False, type=str, help="input of inibitor: None, 'osm' 'path/to/file'")
parser.add_argument("--buffer_inhibidores", dest="buffer_inhib", required=False, type=int, help="metros de buffer aplicado a los inhibidores")

parser.add_argument("--disinhit", dest="disinhit", required=True, type=int, help="desinhibir o no la red")
parser.add_argument("--disinhitor_input", dest="disinhitor_input", required=False, type=str, help="input of dishinibitor: None, 'osm' 'path/to/file' ")
parser.add_argument("--buffer_disinhibitor", dest="buffer_desinhib", required=False, type=int, help="metros de buffer aplicado a los desinhibidores")

parser.add_argument("--proye", dest="proye", required=False, type=int, help="filter by parameter proye")
parser.add_argument("--ci_o_cr", dest="ci_o_cr", required=False, type=int, help="filter by parameter ci_o_cr or 'bikepath or cross path'")
parser.add_argument("--op_ci", dest="op_ci", required=False, type=int, help="filter by parameter op_ci operativity of the bikepath")


#load env variables
load_dotenv()

#define variables of
DATABASE_NAME = os.getenv('DATABASE_NAME')
HOST = os.getenv('HOST')
PORT = os.getenv('PORT')
USER = os.getenv('USER')
PASSWORD = os.getenv('PASSWORD')

# Connect to PostgreSQL
conn = utils.create_conn(DATABASE_NAME,HOST,PORT,USER,PASSWORD)


sql_base_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                    'sql-scripts')

data_base_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                    'data')


def data_pipeline(osm_input, ciclo_input, location, srid, inhibit, inhibitor_input, buffer_inhib, disinhit, disinhitor_input, buffer_desinhib, proye, ci_o_cr, op_ci):
    '''
    - Description: Execute the functions in order to get the result 
    - Input: path of csv file, postgres table name of result table, 
    list of queries (str).
    '''
    print(f'the input arg is {osm_input}')
    print(f'and the type is {type(osm_input)}')
    # Create name of tables in db
    osm_table_name = f'{location}_osm'
    ciclo_table_name = f'{location}_ciclos'
    inhibitor_table_name = f'{location}_inhibitor'
    desinhibitor_table_name = f'{location}_desinhibitor'

    # path of base files of Santiago
    osm_base_path = os.path.join(data_base_path,
                                  'ejes_osm_cliped.geojson')
    ciclo_base_path = os.path.join(data_base_path,
                                    'calidad_cliped.geojson')
    inhibitor_base_path = os.path.join(data_base_path,
                                       'highways.geojson')
    desinhibitor_base_path = os.path.join(data_base_path,
                                          'semaforos.geojson')

    # handle argument osm
    utils.handle_path_argument(osm_input,
                               osm_base_path,
                               osm_table_name,
                               'MULTILINESTRING',
                               USER,
                               PASSWORD,
                               HOST,
                               PORT,
                               DATABASE_NAME)

    # handle ciclo argument 
    utils.handle_path_argument(ciclo_input,
                               ciclo_base_path,
                               ciclo_table_name,
                               'MULTILINESTRING',
                               USER,
                               PASSWORD,
                               HOST,
                               PORT,
                               DATABASE_NAME)

    # handle inhibitor argument 
    utils.handle_path_argument(inhibitor_input,
                               inhibitor_base_path,
                               inhibitor_table_name,
                               'MULTILINESTRING',
                               USER,
                               PASSWORD,
                               HOST,
                               PORT,
                               DATABASE_NAME)

    #handle desinhibitor argument
    utils.handle_path_argument(disinhitor_input,
                               desinhibitor_base_path,
                               desinhibitor_table_name,
                               'MULTILINESTRING',
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

    #proye, ci_o_cr, op_ci
    filters = utils.create_filters_string(proye, ci_o_cr,op_ci)
    
    # Add the WHERE clause only if there are filters to apply
    where_clause = f"WHERE {filters}" if filters else ""

    # Read template query and add parameters                                
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(result_name=full_network_name, 
                                  ciclo=ciclo_table_name, 
                                  osm=osm_table_name,
                                  filters=where_clause)


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

    # inhibit network or not 
    if inhibit:
        # Define path to sql query and table names
        sql_file_path_buffer = os.path.join(sql_base_path,
                                'create_buffer.sql')
        inhibitor_input_name = inhibitor_table_name
        inhibitor_result_name = f'{location}_network_inhib_{buffer_inhib}'
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
        if disinhit:
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
        scenery_name = full_network_name #f'{location}_network'

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
    components_table_name = scenery_name+'_components'                           
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(topo=topology_table_name,
                                  table_name=components_table_name)
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
    data_pipeline(args.osm_input, 
                  args.ciclo_input, 
                  args.location,
                  args.srid,
                  args.inhibit,
                  args.inhibitor_input, 
                  args.buffer_inhib, 
                  args.disinhit,
                  args.disinhitor_input, 
                  args.buffer_desinhib,
                  args.proye,
                  args.ci_o_cr,
                  args.op_ci
                  )

if __name__=='__main__':
    main()

