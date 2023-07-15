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
USER = os.getenv('DB_USER')
PASSWORD = os.getenv('DB_PASSWORD')
# other parameters
H3_LEVEL = os.getenv('H3_LEVEL')
RADIUS_ACCESS = os.getenv('RADIUS_ACCESS')
HIGH_IMPEDANCE = os.getenv('HIGH_IMPEDANCE')
MEDIUM_IMPEDANCE = os.getenv('MEDIUM_IMPEDANCE')
LOW_IMPEDANCE = os.getenv('LOW_IMPEDANCE')
ELSE_IMPEDANCE = os.getenv('ELSE_IMPEDANCE')

# Connect to PostgreSQL
conn = utils.create_conn(DATABASE_NAME,HOST,PORT,USER,PASSWORD)


sql_base_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                    'sql-scripts')

data_base_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                    'data')


def data_pipeline(osm_input, ciclo_input, location_input, srid, inhibit, inhibitor_input, buffer_inhib, disinhit, disinhitor_input, buffer_desinhib, proye, ci_o_cr, op_ci):
    '''
    - Description: Execute the functions in order to get the result 
    - Input: path of csv file, postgres table name of result table, 
    list of queries (str).
    '''

    #create an abbreviated name for handle the area
    location_prefix = utils.create_abbreviation(location_input)

    osm_table_name = f'{location_prefix}_osm'
    ciclo_table_name = f'{location_prefix}_ciclos'
    inhibitor_table_name = f'{location_prefix}_inhibitor'
    desinhibitor_table_name = f'{location_prefix}_desinhibitor'

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
    utils.handle_path_argument('osm',
                               osm_input,
                               osm_base_path,
                               osm_table_name,
                               location_input,
                               'LineString',
                               srid,
                               USER,
                               PASSWORD,
                               HOST,
                               PORT,
                               DATABASE_NAME)

    #add impedance to osm
    path_modify_impedance = os.path.join(sql_base_path,
                                'modify_impedance.sql')
    query_modify_impedance = utils.read_sql_file(path_modify_impedance)
    query = query_modify_impedance.format(table_name=osm_table_name)
    # Execute query formated
    print('modify impedance column')
    utils.execute_query(conn, query)

    # handle ciclo argument 
    utils.handle_path_argument('bike',
                               ciclo_input,
                               ciclo_base_path,
                               ciclo_table_name,
                               location_input,
                               'LineString',
                               srid,
                               USER,
                               PASSWORD,
                               HOST,
                               PORT,
                               DATABASE_NAME)

    # handle inhibitor argument 
    utils.handle_path_argument('inhibitor',
                               inhibitor_input,
                               inhibitor_base_path,
                               inhibitor_table_name,
                               location_input,
                               'LineString',
                               srid,
                               USER,
                               PASSWORD,
                               HOST,
                               PORT,
                               DATABASE_NAME)

    #handle desinhibitor argument
    utils.handle_path_argument('deshinibitor',
                               disinhitor_input,
                               desinhibitor_base_path,
                               desinhibitor_table_name,
                               location_input,
                               'POINT',
                               srid,
                               USER,
                               PASSWORD,
                               HOST,
                               PORT,
                               DATABASE_NAME)



# inhibit network or not 
    if inhibit:
        # Define path to sql query and table names
        sql_file_path_buffer = os.path.join(sql_base_path,
                                'create_impedance_buffers.sql')
        impedance_result_name = f'{location_prefix}_impedance_{buffer_inhib}_buff'
        query_template_buffer = utils.read_sql_file(sql_file_path_buffer)
        # Format sql query
        query = query_template_buffer.format(result_table=impedance_result_name, 
                                  table_name=inhibitor_table_name, 
                                  dist_buffer=buffer_inhib,
                                  high_impedance=HIGH_IMPEDANCE,
                                  medium_impedance=MEDIUM_IMPEDANCE,
                                  low_impedance=LOW_IMPEDANCE,
                                  else_impedance=ELSE_IMPEDANCE,
                                  ) 
        # Execute query formated
        print('Creating impedance buffer')
        utils.execute_query(conn, query)
        

        # Define path to sql query and table names
        sql_file_path_buffer = os.path.join(sql_base_path,
                                'create_buffer.sql')
        inhibitor_result_name = f'{location_prefix}_inhib_{buffer_inhib}_buff'
        query_template_buffer = utils.read_sql_file(sql_file_path_buffer)
        # Format sql query
        query = query_template_buffer.format(result_table=inhibitor_result_name, 
                                  table_name=inhibitor_table_name, 
                                  dist_buffer=buffer_inhib
                                  ) 
        
                                  
        # Execute query formated
        print('Creating inhibitor buffer')
        utils.execute_query(conn, query)
        
        
        # CASE: inhib and deshinib
        if disinhit:
            desinhibitor_input_name = desinhibitor_table_name
            desinhibitor_result_name = f'{location_prefix}_inhib_{buffer_inhib}_desinhib_{buffer_desinhib}_buff'
            # Format sql query
            query = query_template_buffer.format(result_table=desinhibitor_result_name, 
                                      table_name=desinhibitor_input_name, 
                                      dist_buffer=buffer_desinhib
                                      ) 

            # Execute query formated
            print('Creating desinhibitor buffer')
            utils.execute_query(conn, query)

            # Creating final impedance buffer
            sql_file_path_final_buffer = os.path.join(sql_base_path,
                                'buffer_difference.sql')
            buffer_impedance_input_name = f'{location_prefix}_impedance_{buffer_inhib}_desinhib_{buffer_desinhib}_diff'
            buffer_inhib_input_name = f'{location_prefix}_inhib_{buffer_inhib}_desinhib_{buffer_desinhib}_diff'
            query_template_final_buffer = utils.read_sql_file(sql_file_path_final_buffer)
            # Format sql query
            query = query_template_final_buffer.format(impedance_name=buffer_impedance_input_name,
                                                       inhib_name=buffer_inhib_input_name, 
                                      buffer_inhibitor=inhibitor_result_name,
                                      buffer_impedance=impedance_result_name, 
                                      buffer_desinhibitor=desinhibitor_result_name
                                      ) 

            # Execute query formated
            print('Calculating buffer difference')
            utils.execute_query(conn, query)

            # delete_line_segments_in_polygon
            sql_file_path_inhibit_network = os.path.join(sql_base_path,
                                        'create_inhibited_network.sql')
            scenery_name = f'{location_prefix}_inh_{buffer_inhib}_desinh_{buffer_desinhib}_final'
            query_template_inhibit_network = utils.read_sql_file(sql_file_path_inhibit_network)
            # Format sql query
            query = query_template_inhibit_network.format(result_name=scenery_name, 
                                      network_table=osm_table_name, 
                                      impedance_buffer=buffer_impedance_input_name,
                                      inhib_buffer=buffer_inhib_input_name
                                      )
            # Execute query formated
            print('Inhibiting the network')
            utils.execute_query(conn, query)
        # Case: Just ihbin
        else:
            print('desinhibitor are not processing')

            sql_file_path_inhibit_network = os.path.join(sql_base_path,
                                        'create_inhibited_network.sql')
            scenery_name = f'{location_prefix}_inhib_{buffer_inhib}_final'
            query_template_inhibit_network = utils.read_sql_file(sql_file_path_inhibit_network)
            # Format sql query
            query = query_template_inhibit_network.format(result_name=scenery_name, 
                                      network_table=osm_table_name,
                                      impedance_buffer=impedance_result_name,
                                      inhib_buffer=inhibitor_result_name                                      
                                      )
            # Execute query formated
            print('Inhibiting the network')
            utils.execute_query(conn, query)

            #final_table_name = inhibitor_result_name


    #CASE: don't inhib or desinhib
    else:
        print('Not inhibition applied')
        scenery_name = osm_table_name   
    
    ####### AGREGAR OPCIÓN SIN CICLO ######

    # Read SQL file and format query string
    sql_file_path = os.path.join(sql_base_path,
                                'create_full_network.sql')

    #proye, ci_o_cr, op_ci
    filters = utils.create_filters_string(proye, ci_o_cr,op_ci)
    
    # Add the WHERE clause only if there are filters to apply
    # ex. proye = 0 AND ci_o_cr = 0
    where_clause = f"WHERE {filters}" if filters else ""

    suffix_full_network = utils.create_suffix_string(proye, ci_o_cr,op_ci)
    
    # Merge ciclo and vial network
    full_network_name = f'{scenery_name}_full_network{suffix_full_network}'
    

    # Read template query and add parameters                                
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(result_name=full_network_name, 
                                  ciclo=ciclo_table_name, 
                                  osm=scenery_name,
                                  filters=where_clause)


    # Execute query to create full network
    print('Creating intermodal network')
    utils.execute_query(conn, query)
    
    # Create Spatial index for the full network
    sql_file_path = os.path.join(sql_base_path,
                                'create_spatial_index.sql')
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(layer_name=full_network_name, 
                                  schema_name='public')
  

    # Create and clean the topology for inhibited network (impedance =< 1)
    topology_table_name = scenery_name+'_topo'
    # Read SQL file and format query string
    sql_file_path = os.path.join(sql_base_path,
                                'create_clean_topology.sql')

    # Read template query and add parameters                                
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(topo=topology_table_name,
                                  table=full_network_name,
                                  srid=srid)
    print('Creating topology')
    utils.execute_query(conn, query)

    # Calculate Components
    sql_file_path = os.path.join(sql_base_path,
                                'calculate_components.sql')

    # Read template query and add parameters
    components_table_name = scenery_name+'_components'                           
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(topo_name=topology_table_name,
                                  result_table=components_table_name,
                                  table_name=full_network_name)
    print('Calculating components')
    utils.execute_query(conn, query)

    # Calculate Accessibility
    #Create h3 polygons
    #parametrizar h3_level
    utils.download_h3(osm_table_name,srid,H3_LEVEL,USER,PASSWORD,HOST,PORT,DATABASE_NAME)
    
    #Add ID to H3 Polygons
    sql_file_path = os.path.join(sql_base_path,
                                 'create_index.sql')
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(table_name = osm_table_name+'_h3')
    utils.execute_query(conn, query)
    
    # Read SQL file and format query string
    sql_file_path = os.path.join(sql_base_path,
                                'calculate_accessibility.sql')

    #define node table
    node_table_name = f'{topology_table_name}.node'

    # Read template query and add parameters                                
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(h3_table_name=osm_table_name+'_h3',
                                  topo_name=topology_table_name,
                                  radius = RADIUS_ACCESS, #parametrizar
                                  srid=srid,
                                  table_name=full_network_name,
                                  node_table=node_table_name)

    print('Creating accessibility topology')
    utils.execute_query(conn, query)

    # OSM lengths to Hexagons
    # Read SQL file and format query string
    sql_file_path = os.path.join(sql_base_path,
                                'osm_data_to_h3.sql')
    
    #Read template query and add parameters
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(osm_table = osm_table_name,
                                  h3_table = osm_table_name+'_h3')
    print('Adding OSM lenghts to H3')
    utils.execute_query(conn,query)

    # Ciclo lenghts to Hexagons
    # Read SQL file and format query string
    sql_file_path = os.path.join(sql_base_path,
                                 'ciclo_data_to_h3.sql')
    
    # Read template query and add parameters
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(ciclo_table = ciclo_table_name,
                                  h3_table = osm_table_name+'_h3')
    print('Adding Ciclo data to H3')
    utils.execute_query(conn,query)

    # Component result to Hexagons
    # Read SQL file and format query string
    sql_file_path = os.path.join(sql_base_path,
                                 'components_data_to_h3.sql')
    
    # Read template query and add parameters
    query_template = utils.read_sql_file(sql_file_path)
    query = query_template.format(component_table = components_table_name,
                                  h3_table = osm_table_name+'_h3',
                                  result_table = full_network_name)
    print('Adding component result to H3')
    utils.execute_query(conn,query)


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

