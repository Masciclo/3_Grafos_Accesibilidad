# Autor: Matias Duran Niedbalski.
# E-mail: matias.duran@usach.cl
# Fecha: enero, 2022
# 
# Descripcion: Este archivo contiene el flujo de ejecucion para implementar el
# algoritmo de analisis de indicadores y metricas de red sobre redes de
# ciclovias.
#
# Indice -----------------------------------------------------------------------
# 0. Importacion de librerias y funciones.
# 1. Lectura de archivos de entrada (formato *.shp o *.geojson).
# 2. Preproceso y limpieza de geometrías.
# 3. Conversión de tipo de dato sf a tipo de dato igraph (tidygraph).
# 4. Filtro de dataset según escenario.
# 5. Cálculo de indicadores
# 5.1. Se agrega un identificador de componente a cada arco.
# 5.2. Calcula indicadores para el caso general.
# 5.3. Calcula indicadores para cada subcomponente.
# 5.3.1. Casos operativos; gi_comp: id_c|largo_t|largo_prom|beta_index|diametro|
#                                   n_sub_comp
# 5.3.2. Casos inoperativos; gsub_inop_comp:  id_c_sub_inop|id_c|largo_t|
#                                             largo_prom|c_close|c_betwee|
#                                             c_straigth
# 5.3.3. Casos proyectados: gsub_pro_co:  id_c_sub_pro|id_c|largo_t|largo_prom|
#                                         c_close|c_betwee|c_straigth
# 5.4. Count the number of subcomponents for each component
# 6. Exportación de archivos en formato *.csv y *.geojson.
# 6.1. gi_comp: id_component|largo_t|largo_prom|beta_index|diametro|
#               c_betweenness|c_closeness|c_straightness|n_gsub_op_comp|
#               n_gsub_inop_comp|n_gsub_pro_com
# 6.2. gsub_op_comp:  id_component|largo_t|largo_prom|beta_index|diametro|
#                     c_betweenness|c_closeness|c_straightness
# 6.3. gsub_inop_comp:  id_component|largo_t|largo_prom|beta_index|diametro|
#                       c_betweenness|c_closeness|c_straightness
# 6.4. gsub_pro_com:  id_component|largo_t|largo_prom|beta_index|diametro|
#                     c_betweenness|c_closeness|c_straightness
# 6.5. gi_aristas (tabla CSV):  from|to|id_aris|id_2|id_c|weight|id_c_sub_op|
#                               eb_sub_op|ec_sub_op|es_sub_op|d_sub_op|
#                               id_c_sub_inop|eb_sub_inop|ec_sub_inop|
#                               es_sub_inop|d_sub_inop|id_c_sub_pro|
#                               eb_sub_pr|ec_sub_pr|es_sub_pr|d_sub_pr
# 6.6. gi_aristas (tabla GeoJSON):  from|to|id_aris|id_2|id_c|weight|id_c_sub_op|
#                                   eb_sub_op|ec_sub_op|es_sub_op|d_sub_op|
#                                   id_c_sub_inop|eb_sub_inop|ec_sub_inop|
#                                   es_sub_inop|d_sub_inop|id_c_sub_pro|
#                                   eb_sub_pr|ec_sub_pr|es_sub_pr|d_sub_pr
# 6.7. Exportacion de un archivo geojson por cada componente.

# 0. Importacion de librerias y funciones -------------------------------------
library(here)        # Gestionar rutas relativas
library(dplyr)       # Trabajar con dataframes
library(sf)          # Trabajar con simple features
library(igraph)      # Construir grafos
library(tidygraph)   # Manipular grafos en formato de tablas
library(lwgeom)      # Para utilizar la funcion st_split()

# -----------------------------------------------------------------------------
# ruta de carpeta en donde se localiza el archivo "calculate_metrics.R"
# por ejemplo, en este caso el archivo estria en:
#   c:/ruta/del/archivo/calculate_metrics.R
# y la ruta de la carpeta seria:
#   c:/ruta/del/archivo/
setwd('D:/+CICLO/repos/planarize/mas-ciclo/shp_graph_metrics')
# -----------------------------------------------------------------------------

source(file = here('src/graph_helpers.R'))
source(file = here('config.R'))

# Algoritmo y ejecucion --------------------------------------------------------
# 1. Lectura de archivos de entrada (formato *.shp o *.geojson). ---------------
# bicycle_network_gdf = join_polylines(sf::st_read(CICLO_SHP_PATH), sf::st_read(OSM_SHP_PATH))
bicycle_network_gdf = sf::st_read(CICLO_SHP_PATH)
bicycle_network_gdf = bicycle_network_gdf[!sf::st_is_empty(bicycle_network_gdf$geometry),]
names(bicycle_network_gdf) = tolower(names(bicycle_network_gdf))

# Validar columnas obligatorias
missing_fields = !(compulsory_fields %in% names(bicycle_network_gdf))
if (any(missing_fields)) {
  print(paste('Faltan algunas columnas obligatorias en el Dataframe:', compulsory_fields[missing_fields]))
}

# 2. Preproceso y limpieza de geometrías. --------------------------------------
bicycle_network_gdf = split_polylines(
  bicycle_network_gdf,
  id_field='id_2'
)

x_osm_splitter = split_polylines(
  sf::st_read(OSM_SHP_PATH),
  id_field='id_osm'
)


# 3. split con red de calles:
# 3.1. Limpia red de calles aplicando inhibidores y deshinibidores.
x_osm_splitter = apply_disablers (
  x_osm = sf::st_read(OSM_SHP_PATH),
  disablers_list = list(
    sf::st_read('data/raw/65f69d7c-a0ee-4ff5-b220-0168a3c2b756202041-1-16ubwo1.mcsv.shp'),
    sf::st_read('data/raw/Primary_seconday.shp')
  ),
  enablers_list = list(
    sf::st_read('data/raw/Semaforos.shp')
  ),
  enabler_buffer_threshold = 10,
  disabler_buffer_threshold = 10
)

# 3.3 Split de red de calles
x_osm_splitter = split_polylines(
  x_osm_splitter,
  id_field='id_osm'
)


# 3.2. Ejecuta el split con la red de calles
bicycle_network_gdf = split_by_other_polylines(
  bicycle_network_gdf,
  x_osm_splitter,
  id_field='id_2',
)

# 3.3 Unión con red de OSM
total_network_gdf = sf::st_union(
  bicycle_network_gdf,
  x_osm_splitter,
  by_feature = F
)

sf::write_sf(total_network_gdf,"planarizev1.geojson")
sf::

# 3. Conversión de tipo de dato sf a tipo de dato igraph (tidygraph). ----------
total_igraph_raw = sf_to_igraph(
  total_network_gdf,
  directed = FALSE
)

# 4. Filtro de dataset según escenario. ----------------------------------------
# Primero se filtran los no existentes.
bicycle_igraph = bicycle_igraph_raw %>%
  activate(edges) %>%
  filter(!eval(settings_list[[selected_setting]]$filter_non_existent)) %>%
  activate(nodes) %>%
  filter(!node_is_isolated())
  

# 5. Cálculo de indicadores ----------------------------------------------------

# 5.1. Se agrega un identificador de componente a cada arco. -------------------
bicycle_igraph = bicycle_igraph %>%
  add_components(field_name='id_comp')

# 5.2. Calcula indicadores para el caso general. -------------------------------
gi_aristas = bicycle_igraph %>%
  activate(edges) %>%
  mutate(edge_betweenness = estimate_edge_betweenness(., weights=get.edge.attribute(., 'weight'), cutoff=0)) %>%
  add_edge_closeness(field_closeness='edge_closeness', closeness_mode="all", local_cutoff=0) %>%
  add_straightness(field_straightness='edge_straightness', cutoff=0) %>%
  mutate(local_betweenness = estimate_edge_betweenness(., weights=get.edge.attribute(., 'weight'), cutoff=LOCAL_CUTOFF)) %>%
  add_edge_closeness(field_closeness='local_closeness', closeness_mode="all", local_cutoff=LOCAL_CUTOFF) %>%
  add_straightness(field_straightness='local_straightness', cutoff=LOCAL_CUTOFF) %>%
  add_diameter_of_network_components(field_components_name='id_comp', field_diameter_name='diameter')

gi_comp = gi_aristas %>%
  calculate_components_attributes(field_components_name='id_comp')

# 5.3. Calcula indicadores para cada subcomponente. ---------------------------
# 5.3.1. Casos operativos; gi_comp: id_c|largo_t|largo_prom|beta_index|diametro|
#                                   n_sub_comp
gsub_op_comp_igraph = bicycle_igraph %>%
  activate(edges) %>%
  filter(!eval(settings_list[[selected_setting]]$filter_inoperative)) %>%
  activate(nodes) %>%
  filter(!node_is_isolated()) %>%
  add_components(field_name='id_c_sub_op') %>%
  activate(edges) %>%
  mutate(edge_betweenness = estimate_edge_betweenness(., weights=get.edge.attribute(., 'weight'), cutoff=0)) %>%
  add_edge_closeness(field_closeness='edge_closeness', closeness_mode="all", local_cutoff=0) %>%
  add_straightness(field_straightness='edge_straightness', cutoff=0) %>%
  mutate(local_betweenness = estimate_edge_betweenness(., weights=get.edge.attribute(., 'weight'), cutoff=LOCAL_CUTOFF)) %>%
  add_edge_closeness(field_closeness='local_closeness', closeness_mode="all", local_cutoff=LOCAL_CUTOFF) %>%
  add_straightness(field_straightness='local_straightness', cutoff=LOCAL_CUTOFF) %>%
  add_diameter_of_network_components(field_components_name='id_c_sub_op', field_diameter_name='diameter')

gsub_op_comp = gsub_op_comp_igraph %>%
  calculate_components_attributes(field_components_name='id_c_sub_op')


# 5.3.2. Casos inoperativos; gsub_inop_comp:  id_c_sub_inop|id_c|largo_t|
#                                             largo_prom|c_close|c_betwee|
#                                             c_straigth
gsub_inop_comp_igraph = bicycle_igraph %>%
  activate(edges) %>%
  filter(eval(settings_list[[selected_setting]]$filter_inoperative)) %>%
  activate(nodes) %>%
  filter(!node_is_isolated()) %>%
  add_components(field_name='id_c_sub_inop') %>%
  activate(edges) %>%
  mutate(edge_betweenness = estimate_edge_betweenness(., weights=get.edge.attribute(., 'weight'), cutoff=0)) %>%
  add_edge_closeness(field_closeness='edge_closeness', closeness_mode="all", local_cutoff=0) %>%
  add_straightness(field_straightness='edge_straightness', cutoff=0) %>%
  mutate(local_betweenness = estimate_edge_betweenness(., weights=get.edge.attribute(., 'weight'), cutoff=LOCAL_CUTOFF)) %>%
  add_edge_closeness(field_closeness='local_closeness', closeness_mode="all", local_cutoff=LOCAL_CUTOFF) %>%
  add_straightness(field_straightness='local_straightness', cutoff=LOCAL_CUTOFF) %>%
  add_diameter_of_network_components(field_components_name='id_c_sub_inop', field_diameter_name='diameter')

gsub_inop_comp = gsub_inop_comp_igraph %>%
  calculate_components_attributes(field_components_name='id_c_sub_inop')


# 5.3.3. Casos proyectados: gsub_pro_co:  id_c_sub_pro|id_c|largo_t|largo_prom|
#                                         c_close|c_betwee|c_straigth
gsub_pro_com_igraph = bicycle_igraph %>%
  activate(edges) %>%
  filter(eval(settings_list[[selected_setting]]$filter_projected)) %>%
  activate(nodes) %>%
  filter(!node_is_isolated()) %>%
  add_components(field_name='id_c_sub_pro') %>%
  activate(edges) %>%
  mutate(edge_betweenness = estimate_edge_betweenness(., weights=get.edge.attribute(., 'weight'), cutoff=0)) %>%
  add_edge_closeness(field_closeness='edge_closeness', closeness_mode="all", local_cutoff=0) %>%
  add_straightness(field_straightness='edge_straightness', cutoff=0) %>%
  mutate(local_betweenness = estimate_edge_betweenness(., weights=get.edge.attribute(., 'weight'), cutoff=LOCAL_CUTOFF)) %>%
  add_edge_closeness(field_closeness='local_closeness', closeness_mode="all", local_cutoff=LOCAL_CUTOFF) %>%
  add_straightness(field_straightness='local_straightness', cutoff=LOCAL_CUTOFF) %>%
  add_diameter_of_network_components(field_components_name='id_c_sub_pro', field_diameter_name='diameter')

gsub_pro_com = gsub_pro_com_igraph %>%
  calculate_components_attributes(field_components_name='id_c_sub_pro')

# 5.4. Count the number of subcomponents for each component --------------------
n_gsub_op_comp = gsub_op_comp_igraph %>%
  activate(edges) %>%
  as_tibble() %>%
  group_by(id_comp) %>%
  summarize(n_gsub_op_comp=n_distinct(id_c_sub_op))

n_gsub_inop_comp = gsub_inop_comp_igraph %>%
  activate(edges) %>%
  as_tibble() %>%
  group_by(id_comp) %>%
  summarize(n_gsub_inop_comp=n_distinct(id_c_sub_inop))

n_gsub_pro_com = gsub_pro_com_igraph %>%
  activate(edges) %>%
  as_tibble() %>%
  group_by(id_comp) %>%
  summarize(n_gsub_pro_com=n_distinct(id_c_sub_pro))

gi_comp = gi_comp %>%
  left_join(n_gsub_op_comp, by=c(id_component='id_comp')) %>%
  left_join(n_gsub_inop_comp, by=c(id_component='id_comp')) %>%
  left_join(n_gsub_pro_com, by=c(id_component='id_comp'))

# 6. Exportación de archivos en formato *.csv y *.geojson. ---------------------

output_folder = file.path(OUTPUT_PATH)
output_setting_folder = file.path(output_folder, selected_setting)

unlink(output_setting_folder, recursive = TRUE,force = T)

dir.create(output_folder, showWarnings = FALSE)
dir.create(output_setting_folder, showWarnings = FALSE)

# 6.1. gi_comp: id_component|largo_t|largo_prom|beta_index|diametro|
#               c_betweenness|c_closeness|c_straightness|n_gsub_op_comp|
#               n_gsub_inop_comp|n_gsub_pro_com
gi_comp %>%
  write.csv(file=file.path(output_setting_folder, 'gi_comp.csv'))

# 6.2. gsub_op_comp:  id_component|largo_t|largo_prom|beta_index|diametro|
#                     c_betweenness|c_closeness|c_straightness
gsub_op_comp %>%
  write.csv(file=file.path(output_setting_folder, 'gsub_op_comp.csv'))

# 6.3. gsub_inop_comp:  id_component|largo_t|largo_prom|beta_index|diametro|
#                       c_betweenness|c_closeness|c_straightness
gsub_inop_comp %>%
  write.csv(file=file.path(output_setting_folder, 'gsub_inop_comp.csv'))

# 6.4. gsub_pro_com:  id_component|largo_t|largo_prom|beta_index|diametro|
#                     c_betweenness|c_closeness|c_straightness
gsub_pro_com %>%
  write.csv(file=file.path(output_setting_folder, 'gsub_pro_com.csv'))

# 6.5. gi_aristas (tabla CSV):  from|to|id_aris|id_2|id_c|weight|id_c_sub_op|
#                               eb_sub_op|ec_sub_op|es_sub_op|d_sub_op|
#                               id_c_sub_inop|eb_sub_inop|ec_sub_inop|
#                               es_sub_inop|d_sub_inop|id_c_sub_pro|
#                               eb_sub_pr|ec_sub_pr|es_sub_pr|d_sub_pr
gi_comp_table = gi_aristas %>%
  activate(edges) %>%
  as_tibble() %>%
  select(c(edgeID, id_comp))

gsub_op_comp_table = gsub_op_comp_igraph %>%
  activate(edges) %>%
  as_tibble() %>%
  select(c(edgeID, id_c_sub_op,
           eb_sub_op=edge_betweenness,
           ec_sub_op=edge_closeness,
           es_sub_op=edge_straightness,
           ebl_sub_op=local_betweenness,
           ecl_sub_op=local_closeness,
           esl_sub_op=local_straightness,
           d_sub_op=diameter))

gsub_inop_comp_table = gsub_inop_comp_igraph %>%
  activate(edges) %>%
  as_tibble() %>%
  select(c(edgeID, id_c_sub_inop,
           eb_sub_inop=edge_betweenness,
           ec_sub_inop=edge_closeness,
           es_sub_inop=edge_straightness,
           ebl_sub_inop=local_betweenness,
           ecl_sub_inop=local_closeness,
           esl_sub_inop=local_straightness,
           d_sub_inop=diameter))

gsub_pro_com_table = gsub_pro_com_igraph %>%
  activate(edges) %>%
  as_tibble() %>%
  select(c(edgeID, id_c_sub_pro,
           eb_sub_pr=edge_betweenness,
           ec_sub_pr=edge_closeness,
           es_sub_pr=edge_straightness,
           ebl_sub_pr=local_betweenness,
           ecl_sub_pr=local_closeness,
           esl_sub_pr=local_straightness,
           d_sub_pr=diameter))

bicycle_igraph_raw %>%
  activate(edges) %>%
  as_tibble() %>%
  left_join(gi_comp_table, by='edgeID') %>%
  left_join(gsub_op_comp_table, by='edgeID') %>%
  left_join(gsub_inop_comp_table, by='edgeID') %>%
  left_join(gsub_pro_com_table, by='edgeID') %>%
  select(
    all_of(compulsory_fields),
    from=from,
    to=to,
    id_aris=edgeID,
    id_2=id_2,
    id_c=id_comp,
    weight=weight,
    id_c_sub_op=id_c_sub_op,
    eb_sub_op=eb_sub_op,
    ec_sub_op=ec_sub_op,
    es_sub_op=es_sub_op,
    ebl_sub_op=ebl_sub_op, # indices locales
    ecl_sub_op=ecl_sub_op, # indices locales
    esl_sub_op=esl_sub_op, # indices locales
    d_sub_op=d_sub_op,
    id_c_sub_inop=id_c_sub_inop,
    eb_sub_inop=eb_sub_inop,
    ec_sub_inop=ec_sub_inop,
    es_sub_inop=es_sub_inop,
    ebl_sub_inop=ebl_sub_inop, # indices locales
    ecl_sub_inop=ecl_sub_inop, # indices locales
    esl_sub_inop=esl_sub_inop, # indices locales
    d_sub_inop=d_sub_inop,
    id_c_sub_pro=id_c_sub_pro,
    eb_sub_pr=eb_sub_pr,
    ec_sub_pr=ec_sub_pr,
    es_sub_pr=es_sub_pr,
    ebl_sub_pr=ebl_sub_pr, # indices locales
    ecl_sub_pr=ecl_sub_pr, # indices locales
    esl_sub_pr=esl_sub_pr, # indices locales
    d_sub_pr=d_sub_pr
  ) %>%
  write.csv(file=file.path(output_setting_folder, 'gi_aristas.csv'))

# 6.6. gi_aristas (tabla GeoJSON):  from|to|id_aris|id_2|id_c|weight|id_c_sub_op|
#                                   eb_sub_op|ec_sub_op|es_sub_op|d_sub_op|
#                                   id_c_sub_inop|eb_sub_inop|ec_sub_inop|
#                                   es_sub_inop|d_sub_inop|id_c_sub_pro|
#                                   eb_sub_pr|ec_sub_pr|es_sub_pr|d_sub_pr

bicycle_igraph_raw %>%
  activate(edges) %>%
  as_tibble() %>%
  left_join(gi_comp_table, by='edgeID') %>%
  left_join(gsub_op_comp_table, by='edgeID') %>%
  left_join(gsub_inop_comp_table, by='edgeID') %>%
  left_join(gsub_pro_com_table, by='edgeID') %>%
  select(
    all_of(compulsory_fields),
    from=from,
    to=to,
    id_aris=edgeID,
    id_2=id_2,
    id_c=id_comp,
    weight=weight,
    id_c_sub_op=id_c_sub_op,
    eb_sub_op=eb_sub_op,
    ec_sub_op=ec_sub_op,
    es_sub_op=es_sub_op,
    ebl_sub_op=ebl_sub_op, # indices locales
    ecl_sub_op=ecl_sub_op, # indices locales
    esl_sub_op=esl_sub_op, # indices locales
    d_sub_op=d_sub_op,
    id_c_sub_inop=id_c_sub_inop,
    eb_sub_inop=eb_sub_inop,
    ec_sub_inop=ec_sub_inop,
    es_sub_inop=es_sub_inop,
    ebl_sub_inop=ebl_sub_inop, # indices locales
    ecl_sub_inop=ecl_sub_inop, # indices locales
    esl_sub_inop=esl_sub_inop, # indices locales
    d_sub_inop=d_sub_inop,
    id_c_sub_pro=id_c_sub_pro,
    eb_sub_pr=eb_sub_pr,
    ec_sub_pr=ec_sub_pr,
    es_sub_pr=es_sub_pr,
    ebl_sub_pr=ebl_sub_pr, # indices locales
    ecl_sub_pr=ecl_sub_pr, # indices locales
    esl_sub_pr=esl_sub_pr, # indices locales
    d_sub_pr=d_sub_pr,
    geometry=geometry
  ) %>%
  sf::st_write(file.path(output_setting_folder, 'gi_aristas.geojson'), append = FALSE)

# 6.7. Exportar un archivo json por cada componente. ---------------------------

# 6.7.1. Arcos operativos
operative_edges_path = file.path(output_setting_folder, 'operative_edges')
unlink(here(operative_edges_path), recursive = TRUE,force = T)
dir.create(here(operative_edges_path), showWarnings = FALSE)

for (c in unique(gsub_op_comp_table$id_c_sub_op)) {
  bicycle_igraph_raw %>%
    activate(edges) %>%
    as_tibble() %>%
    left_join(gi_comp_table, by='edgeID') %>%
    left_join(gsub_op_comp_table, by='edgeID') %>%
    left_join(gsub_inop_comp_table, by='edgeID') %>%
    left_join(gsub_pro_com_table, by='edgeID') %>%
    filter(id_c_sub_op == c) %>%
    select(
      all_of(compulsory_fields),
      from=from,
      to=to,
      id_aris=edgeID,
      id_2=id_2,
      id_c=id_comp,
      weight=weight,
      id_c_sub_op=id_c_sub_op,
      eb_sub_op=eb_sub_op,
      ec_sub_op=ec_sub_op,
      es_sub_op=es_sub_op,
      ebl_sub_op=ebl_sub_op, # indices locales
      ecl_sub_op=ecl_sub_op, # indices locales
      esl_sub_op=esl_sub_op, # indices locales
      d_sub_op=d_sub_op,
      id_c_sub_inop=id_c_sub_inop,
      eb_sub_inop=eb_sub_inop,
      ec_sub_inop=ec_sub_inop,
      es_sub_inop=es_sub_inop,
      ebl_sub_inop=ebl_sub_inop, # indices locales
      ecl_sub_inop=ecl_sub_inop, # indices locales
      esl_sub_inop=esl_sub_inop, # indices locales
      d_sub_inop=d_sub_inop,
      id_c_sub_pro=id_c_sub_pro,
      eb_sub_pr=eb_sub_pr,
      ec_sub_pr=ec_sub_pr,
      es_sub_pr=es_sub_pr,
      ebl_sub_pr=ebl_sub_pr, # indices locales
      ecl_sub_pr=ecl_sub_pr, # indices locales
      esl_sub_pr=esl_sub_pr, # indices locales
      d_sub_pr=d_sub_pr,
      geometry=geometry
    ) %>%
    sf::st_write(file.path(operative_edges_path, paste('gi_aristas_', c, '.geojson', sep='')), append = FALSE)
}

# 6.7.2. Arcos inoperativos
inoperative_edges_path = file.path(output_setting_folder, 'inoperative_edges')
unlink(here(inoperative_edges_path), recursive = TRUE,force = T)
dir.create(here(inoperative_edges_path), showWarnings = FALSE)

for (c in unique(gsub_op_comp_table$id_c_sub_inop)) {
  bicycle_igraph_raw %>%
    activate(edges) %>%
    as_tibble() %>%
    left_join(gi_comp_table, by='edgeID') %>%
    left_join(gsub_op_comp_table, by='edgeID') %>%
    left_join(gsub_inop_comp_table, by='edgeID') %>%
    left_join(gsub_pro_com_table, by='edgeID') %>%
    filter(id_c_sub_inop == c) %>%
    select(
      all_of(compulsory_fields),
      from=from,
      to=to,
      id_aris=edgeID,
      id_2=id_2,
      id_c=id_comp,
      weight=weight,
      id_c_sub_op=id_c_sub_op,
      eb_sub_op=eb_sub_op,
      ec_sub_op=ec_sub_op,
      es_sub_op=es_sub_op,
      ebl_sub_op=ebl_sub_op, # indices locales
      ecl_sub_op=ecl_sub_op, # indices locales
      esl_sub_op=esl_sub_op, # indices locales
      d_sub_op=d_sub_op,
      id_c_sub_inop=id_c_sub_inop,
      eb_sub_inop=eb_sub_inop,
      ec_sub_inop=ec_sub_inop,
      es_sub_inop=es_sub_inop,
      ebl_sub_inop=ebl_sub_inop, # indices locales
      ecl_sub_inop=ecl_sub_inop, # indices locales
      esl_sub_inop=esl_sub_inop, # indices locales
      d_sub_inop=d_sub_inop,
      id_c_sub_pro=id_c_sub_pro,
      eb_sub_pr=eb_sub_pr,
      ec_sub_pr=ec_sub_pr,
      es_sub_pr=es_sub_pr,
      ebl_sub_pr=ebl_sub_pr, # indices locales
      ecl_sub_pr=ecl_sub_pr, # indices locales
      esl_sub_pr=esl_sub_pr, # indices locales
      d_sub_pr=d_sub_pr,
      geometry=geometry
    ) %>%
    sf::st_write(file.path(inoperative_edges_path, paste('gi_aristas_', c, '.geojson', sep='')), append = FALSE)
}

# 6.7.3. Arcos proyectados
projected_edges_path = file.path(output_setting_folder, 'projected_edges')
unlink(here(projected_edges_path), recursive = TRUE,force = T)
dir.create(here(projected_edges_path), showWarnings = FALSE)

for (c in unique(gsub_op_comp_table$id_c_sub_pro)) {
  bicycle_igraph_raw %>%
    activate(edges) %>%
    as_tibble() %>%
    left_join(gi_comp_table, by='edgeID') %>%
    left_join(gsub_op_comp_table, by='edgeID') %>%
    left_join(gsub_inop_comp_table, by='edgeID') %>%
    left_join(gsub_pro_com_table, by='edgeID') %>%
    filter(id_c_sub_pro == c) %>%
    select(
      all_of(compulsory_fields),
      from=from,
      to=to,
      id_aris=edgeID,
      id_2=id_2,
      id_c=id_comp,
      weight=weight,
      id_c_sub_op=id_c_sub_op,
      eb_sub_op=eb_sub_op,
      ec_sub_op=ec_sub_op,
      es_sub_op=es_sub_op,
      ebl_sub_op=ebl_sub_op, # indices locales
      ecl_sub_op=ecl_sub_op, # indices locales
      esl_sub_op=esl_sub_op, # indices locales
      d_sub_op=d_sub_op,
      id_c_sub_inop=id_c_sub_inop,
      eb_sub_inop=eb_sub_inop,
      ec_sub_inop=ec_sub_inop,
      es_sub_inop=es_sub_inop,
      ebl_sub_inop=ebl_sub_inop, # indices locales
      ecl_sub_inop=ecl_sub_inop, # indices locales
      esl_sub_inop=esl_sub_inop, # indices locales
      d_sub_inop=d_sub_inop,
      id_c_sub_pro=id_c_sub_pro,
      eb_sub_pr=eb_sub_pr,
      ec_sub_pr=ec_sub_pr,
      es_sub_pr=es_sub_pr,
      ebl_sub_pr=ebl_sub_pr, # indices locales
      ecl_sub_pr=ecl_sub_pr, # indices locales
      esl_sub_pr=esl_sub_pr, # indices locales
      d_sub_pr=d_sub_pr,
      geometry=geometry
    ) %>%
    sf::st_write(file.path(projected_edges_path, paste('gi_aristas_', c, '.geojson', sep='')), append = FALSE)
}
