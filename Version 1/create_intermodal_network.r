# Autor: Matias Duran Niedbalski & Ignacio Hernández C.
# E-mail: matias.duran@usach.cl & ignacio.hernandez.c@usach.cl
# Fecha: agosto, 2022
# 
# Descripcion: Este archivo contiene el flujo de ejecucion para implementar el
# algoritmo de analisis de indicadores y metricas de red sobre redes de
# ciclovias.
#
# Indice -----------------------------------------------------------------------
# 0. Importacion de librerias y funciones.
# 1. Lectura de archivos de entrada (formato *.shp o *.geojson).
# 2. Preproceso y limpieza de geometrías (Ciclovías y OSM).
# 2.1. Split de ciclovías.
# 2.2. Split de OSM.
# 2.3. Split de ciclovías con red OSM.
# 2.4. Unión.
# 3. Conversión de tipo de dato sf a tipo de dato igraph (tidygraph).
# 4. Aplicación de inhibidores y deshinibidores
# 5. Filtro de dataset según escenario.




# 0. Importacion de librerias y funciones -------------------------------------
packages <- c("here","dplyr","sf","igraph","lwgeom")
install.packages(setdiff(packages,rownames(installed.packages())))

library(here)        # Gestionar rutas relativas
library(dplyr)       # Trabajar con dataframes
library(sf)          # Trabajar con simple features
library(igraph)      # Construir grafos
library(lwgeom)      # Para utilizar la funcion st_split()

# -----------------------------------------------------------------------------
# ruta de carpeta en donde se localiza el archivo "calculate_metrics.R"
# por ejemplo, en este caso el archivo estria en:
#   c:/ruta/del/archivo/calculate_metrics.R
# y la ruta de la carpeta seria:
#   c:/ruta/del/archivo/
setwd('~/grafos-accesibilidad/')
# -----------------------------------------------------------------------------

source(file = here('src/graph_helpers.R'))
source(file = here('src/h3_helpers.R'))
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

# 2.1. Split de ciclovías
bicycle_network_gdf = split_polylines(
  bicycle_network_gdf,
  id_field='id_2'
)

# 2.2 Split de calles
x_osm_splitter = split_polylines(
  sf::st_read(OSM_SHP_PATH),
  id_field='OBJECTID'
)

# 2.3. Ejecuta el split de ciclovías con la red de calles
bicycle_network_gdf = split_by_other_polylines(
  bicycle_network_gdf,
  x_osm_splitter,
  id_field='id_2',
)

# 2.4 Unión con red de OSM
total_network_gdf = join_polylines(
  bicycle_network_gdf,
  x_osm_splitter
)


# 3. Ejecuta inhibidores y deshinibidores
total_network_with_enabler_disabler = apply_disablers (
  x_osm = x_osm_splitter,
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

# 4. Conversión de tipo de dato sf a tipo de dato igraph (tidygraph). ----------
total_igraph_raw = sf_to_igraph(
  total_network_gdf,
  directed = F
)

enabler_disabler_igraph_raw = sf_to_igraph(
  total_network_with_enabler_disabler,
  directed = F
)

# 5. Exportación de archivos resultantes
#Shape de redcompleta
sf::write_sf(
  total_network_gdf,
  "data/output/total_network.shp"
  )

#Shape de red con inhibidores y desinhibidores
sf::write_sf(
  total_network_with_enabler_disabler,
  "data/output/gdf/enabler_disabler_network.shp"
  )

write_graph(
  total_igraph_raw,
  "data/output/graphs/total_igraph.txt"
  )

write_graph(
  enabler_disabler_igraph_raw,
  "data/output/graphs/enabler_disabler_igraph.txt"
)