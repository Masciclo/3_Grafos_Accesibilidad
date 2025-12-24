# Autor: Matias Duran Niedbalski.
# E-mail: matias.duran@usach.cl
# Fecha: enero, 2022
# 
# Descripcion: Este archivo contiene funciones auxiliares para la ejecucion del
# flujo definido en el archivo calculate_metrics.R
# En particular, la lista de funciones definidas en este archivo es:
#   - split_polylines: Divide polilineas que se intersectan.
#   - sf_to_igraph: Transforma SF dataframe a Tidygraph (igraph).
#   - add_components: Agrega una columna con el ID del componente al que
#                     pertenece cada arco.
#   - add_diameter_of_network:  Agrega una columna con un 1 si el arco pertenece
#                               al diametro, un 0 en caso contrario.
#   - add_edge_closeness: Agrega closeness a los arcos, promediando el valor de
#                         closeness de sus vertices.
#   - add_diameter_of_network_components: Agrega una columna con un 1 si el
#                 arco pertenece al diametro del componente correspondiente, un
#                 0 en caso contrario.
#   - add_straightness: Agrega una columna a los arcos con el valor de
#                       straightness. Esta es calculada como el promedio de
#                       straightness en los dos nodos (origen y destino).
#   - calculate_components_attributes: Crea un tabla resumen de los componentes
#                       de un grafo, con metricas representativos para cada uno
#                       de ellos.


# Importacion de librerias y funciones -----------------------------------------

library(dplyr)       # Trabajar con dataframes
library(sf)          # Trabajar con simple features
library(igraph)      # Construir grafos
library(tidygraph)   # Manipular grafos en formato de tablas
library(lwgeom)      # Para utilizar la funcion st_split()
library(tibble)

# Librerias utiles pero no utilizadas:
# library(sp)          # Trabajar con datos espaciales
# library(maptools)    # Algunas herramientas para manipular datos geogr?ficos
# library(shp2graph)   # Funciones para pasar objetos de sp a igraph
# library(sfnetworks)  # Funciones para pasar objetos de sf a igraph
# library(ggplot2)     # Visualizaciones
# library(purrr)
# library(rgeos)

PRECISION = 1 # Numero de cifras decimales: 1 = 10 cm; 2 = 1 cm.

# Definicion de funciones ------------------------------------------------------

#' Aplica inhibidores y desinhibidores .
#' 
#' @param x_osm Un data frame con geometry desde OpenStreatMap.
#' @param disablers_list Lista de capas de inhibidores.
#' @param enablers_list Lista de capas de desinhibidores.
#' @param enabler_buffer_threshold Rango del buffer asociado a desinhibidores.
#' @param disabler_buffer_threshold Rango del buffer asociado a inhibidores
#' @return Capa con inhibiores y desinhibidores
#' @examples
#' apply_disablers(osm_shp, list(recorridos_transantiago,calles_principales),list(semaforos),100,100)
apply_disablers = function(
  x_osm,
  disablers_list,
  enablers_list,
  enabler_buffer_threshold,
  disabler_buffer_threshold
) {
  
  #Se asigna el ID de OSM
  x_osm = tibble::rowid_to_column(x_osm, "id_osm")

  #Crea funcion elimina las superposiciones de capas
  st_erase = function(x, y) sf::st_difference(x, sf::st_union(sf::st_make_valid(sf::st_combine(sf::st_make_valid(y)))))
  
  filtered_x_osm = x_osm %>% mutate(enabler_level = 0)
  
  # Enable ways
  #Para cada desinhibidor 
  for (x_enabler in enablers_list) {
    #Se asigna el CRS de la capa OSM a la capa de desinhibidor
    x_enabler_buffer = sf::st_transform(x_enabler, st_crs(filtered_x_osm)) %>% mutate
    #Se crea el buffer siguiendo el tamaño asignado en enabler_buffer_threshold
    x_enabler_buffer = sf::st_buffer(x_enabler_buffer, enabler_buffer_threshold, nQuadSegs=4) #%>%
    
    #Se reduce la precisión de ambas capas para obtener mejores geométricas
    x_enabler_buffer = x_enabler_buffer %>% sf::st_set_precision(1e3)  %>% add_column( level = 1 )
    filtered_x_osm = filtered_x_osm %>% st_set_precision(1e3)
    #x_enabler_buffer = st_union(st_make_valid(x_enabler_buffer))
    
    # it keeps the max value of the enabler
    id_osm_level = sf::st_join(filtered_x_osm, x_enabler_buffer) %>%
      select(c(id_osm, level)) %>%
      as.data.frame() %>%
      select(-geometry) %>%
      group_by(id_osm) %>%
      summarize(level = max(level))

    filtered_x_osm = left_join(filtered_x_osm, id_osm_level, by = 'id_osm', keep = FALSE, na_matches = 'never')
    filtered_x_osm = filtered_x_osm %>%
      mutate(enabler_level = pmax(enabler_level, level)) %>%
      select(-level)
  }
  
  # Disable ways
  for (x_disabler in disablers_list) {
    x_disabler = tibble::rowid_to_column(x_disabler, "id_disabler") %>% add_column( level = sample(0:1,1) ) %>% 
      select(c('id_disabler', 'level'))
    x_disabler_buffer = sf::st_transform(x_disabler, st_crs(filtered_x_osm)) #%>%
    x_disabler_buffer = sf::st_buffer(x_disabler_buffer, disabler_buffer_threshold, nQuadSegs=4) #%>%
    
    # filtered_x_osm[0:1000,][sf::st_intersects(filtered_x_osm[0:1000,], x_inhibitor_buffer, sparse = FALSE),]
    filtered_x_osm = filtered_x_osm %>% st_set_precision(1e3)
    x_disabler_buffer = x_disabler_buffer %>% st_set_precision(1e3) 
    
    deleted_segments = filtered_x_osm %>%
      select(c('id_osm', 'enabler_level')) %>%
      sf::st_intersection(x_disabler_buffer) %>%
      filter(enabler_level <= level) # only segments which must be deleted
    
    filtered_x_osm = filtered_x_osm %>% st_set_precision(1e3)
    deleted_segments = deleted_segments %>%
      st_set_precision(1e3) %>%
      st_buffer(1, nQuadSegs=4)
    
    deleted_segments = st_union(st_make_valid(deleted_segments)) 
    filtered_x_osm = st_erase(sf::st_make_valid(filtered_x_osm), deleted_segments)
    
  }
  
  return (filtered_x_osm)
  
}

#' Une ciclovías con calles de OpenStreatMap
#' 
#' @param x_ciclo Un data frame con geometry.
#' @param x_osm Nombre de columna con id unico para cada geometria.
#' @return Un dataframe con la unión de ciclovías y calles.
#' @export
#' @examples
#' split_polylines(bicycle_network_gdf, id_field='id_2')
join_polylines = function(x_ciclo, x_osm) {
  #x_ciclo = sf::st_read('')
  #x_osm = sf::st_read('')
  
  x_ciclo[, 'source'] = '+ciclo'
  x_osm[, 'source'] = 'osm'
  
  for (column_name in names(x_ciclo)) {
    if (!(column_name %in% c('geometry'))) {
      x_osm[, column_name] = NA
    }
  }
  
  x_osm[, 'ID_2'] = -99999
  
  joined_polylines = rbind (x_ciclo, x_osm[names(x_ciclo)])
  return (joined_polylines)
}

#' Divide polilineas que se intersectan.
#' 
#' @param x Un data frame con geometry.
#' @param id_field Nombre de columna con id unico para cada geometria.
#' @param geom_precision Precision.
#' @return Un dataframe con las polilineas que intersectan subdivididas.
#' @export
#' @examples
#' split_polylines(bicycle_network_gdf, id_field='id_2')
split_by_other_polylines = function(x, y, id_field='id_2', geom_precision=10^PRECISION) {
  
  # Recorre x fila a fila y compara cada fila contra el resto de las filas.
  # si hay intersecciones, subdivide las polilineas. Las filas subdivididas
  # se van almacenando en split_df, que al principio esta vacio.
  
  split_df = data.frame()
  
  for (row in 1:nrow(x)) {
    
    # Muestra que fila se esta procesando, cada 100 filas.
    if (row%%100 == 0) {
      print(paste('Procesando polilinea', row, 'de', nrow(x)))
    }
    
    # Obtiene el id de la fila y el valor de la geometria para dicho id.
    # Ademas, filtered_df contiene todas las filas excluyendo la del id actual.
    row_id = as.data.frame(x)[row, id_field]
    row_geometry = x[row,]
    
    # define la precision para las operaciones geometricas.
    row_geometry = sf::st_set_precision(row_geometry, geom_precision)
    filtered_df = sf::st_set_precision(y, geom_precision)
    
    # Aca se subdividen las polilineas, de ser necesario. Si hay geometrias duplicadas
    # el error se silencia (con silent=T).
    split_lines = try(
      sf::st_collection_extract(lwgeom::st_split(row_geometry, filtered_df), "LINESTRING"),
      silent=T
    )
    
    if (inherits(split_lines, "try-error")) {
      print(row_id)
      split_lines = data.frame()
    }
    
    if (nrow(split_lines) >= 1) {
      split_df = rbind(split_df, as.data.frame(split_lines))
    }
    
  }
  
  # Borra polilineas demasiado pequenas. Al estar fijado en 0, no hace nada, pero puede
  # ser util en el futuro.
  THRESHOLD_SIZE = 0
  small_lines_filter = sf::st_length(split_df$geometry) %>%
    as.numeric()
  small_lines_filter = small_lines_filter > THRESHOLD_SIZE
  
  graph = sf::st_sf(split_df[small_lines_filter,])
  sf::st_write(graph, 'g1.shp', append = FALSE)
  return (graph)
}

#' Divide polilineas que se intersectan.
#' 
#' @param x Un data frame con geometry.
#' @param id_field Nombre de columna con id unico para cada geometria.
#' @param geom_precision Precision.
#' @return Un dataframe con las polilineas que intersectan subdivididas.
#' @export
#' @examples
#' split_polylines(bicycle_network_gdf, id_field='id_2')
split_polylines = function(x, id_field='id_2', geom_precision=10^PRECISION) {
  
  # Recorre x fila a fila y compara cada fila contra el resto de las filas.
  # si hay intersecciones, subdivide las polilineas. Las filas subdivididas
  # se van almacenando en split_df, que al principio esta vacio.

  split_df = data.frame()
  
  for (row in 1:nrow(x)) {
    
    # Muestra que fila se esta procesando, cada 100 filas.
    if (row%%100 == 0) {
      print(paste('Procesando polilinea', row, 'de', nrow(x)))
    }

    # Obtiene el id de la fila y el valor de la geometria para dicho id.
    # Ademas, filtered_df contiene todas las filas excluyendo la del id actual.
    row_id = as.data.frame(x)[row, id_field]
    row_geometry = x[row,]
    
    filtered_df = subset(x, !!dplyr::sym(id_field) != row_id)
    
    # define la precision para las operaciones geometricas.
    row_geometry = sf::st_set_precision(row_geometry, geom_precision)
    filtered_df = sf::st_set_precision(filtered_df, geom_precision)
    
    # Aca se subdividen las polilineas, de ser necesario. Si hay geometrias duplicadas
    # el error se silencia (con silent=T).
    split_lines = try(
      sf::st_collection_extract(lwgeom::st_split(row_geometry, filtered_df), "LINESTRING"),
      silent=T
    )
    
    if (inherits(split_lines, "try-error")) {
      print(row_id)
      split_lines = data.frame()
    }
    
    if (nrow(split_lines) >= 1) {
      split_df = rbind(split_df, as.data.frame(split_lines))
    }
    
  }
  
  # Borra polilineas demasiado pequenas. Al estar fijado en 0, no hace nada, pero puede
  # ser util en el futuro.
  THRESHOLD_SIZE = 0
  small_lines_filter = sf::st_length(split_df$geometry) %>%
    as.numeric()
  small_lines_filter = small_lines_filter > THRESHOLD_SIZE
  
  graph = sf::st_sf(split_df[small_lines_filter,])
  
  return (graph)

}

#' Transforma SF dataframe a Tidygraph (igraph)
#' 
#' @param x Un data frame con geometry.
#' @param directed FALSE si el grafo es no dirigido.
#' @param geom_precision Precision.
#' @return Un objeto tidygraph con el grafo que representa a la red.
#' @export
#' @examples
#' sf_to_igraph(bicycle_network_gdf, directed = FALSE)
sf_to_igraph = function(x, directed = FALSE, geom_precision=PRECISION) {
  
  edges <- x %>%  # Las aristas del grafo son los LINESTRINGS encontrados.
    mutate(edgeID = c(1:n())) %>% # A cada una de estas se le asigna un ?ndice ?nico, 
    # que luego puede relacionarse con su nodo inicial y final.
    mutate(weight = sf::st_length(.$geometry)) # se agrega el weight = distancia de las
    # polilineas (subdivididas, si se les ha aplicado split_polylines() antes)
  
  nodes <- edges %>%        # Los nodos del grafo son los puntos inicial y final de las aristas.
    sf::st_coordinates() %>%    # Encontrar las ubicaciones de los nodos. Se obtiene una matriz.
    as_tibble() %>%         # Pasar la matriz a dataframe.
    rename(edgeID = L1) %>% # Asociar los nodos al nombre de las aristas asignado en el paso anterior 
    group_by(edgeID) %>%    # Seleccionar por aristas
    slice(c(1, n())) %>%    # Vector de indices
    ungroup() %>%           # Tomar los nodos de cada arista
    mutate(start_end = rep(c('start', 'end'), times = n()/2)) %>%  # Nombrar los nodos iniciales y finales
    mutate(X = round(X, geom_precision)) %>% # Estas dos lineas definen la precision de las coordenadas.
    mutate(Y = round(Y, geom_precision)) %>%
    # Cada uno de los nodos del grafo necesita tener un ?ndice ?nico, de modo que puedan relacionarse con las aristas.
    # Se debe tener en cuenta que las aristas pueden compartir puntos de inicio y/o puntos finales.
    # Dichos puntos duplicados, que tienen la misma coordenada X e Y, son un solo nodo y por lo tanto, 
    # deber?an obtener el mismo ?ndice. Tener en cuenta que las coordenadas que se muestran en el tibble
    # est?n redondeados y pueden verse iguales para varias filas, incluso cuando no lo son. 
    # Se usa la funci?n group_indices en dplyr para dar a cada grupo de combinaciones (X,Y) un ?ndice ?nico.
    
    mutate(xy = paste(.$X, .$Y)) %>%    # A?adir los nodos
    mutate(nodeID = group_indices(., factor(xy, levels = unique(xy)))) %>% # A?adir los indices
    select(-xy) # Indicar que lo anterior se realiza para cada nodo
  
  # A cada uno de los nodos iniciales y finales se le ha asignado un ID,
  # de este modo se pueden asociar estos ?ndices con los de las aristas. 
  # En otras palabras, se puede especificar para cada arista, en qu? nodo comienza y en qu? nodo termina. 
  
  # Nodos de inicio
  source_nodes <- nodes %>%           # Seleccionar los nodos
    filter(start_end == 'start') %>%  # Filtrar solo los de inicio
    pull(nodeID)                      # Obtener IDs
  
  # Nodos de fin
  target_nodes <- nodes %>%          # Seleccionar los nodos
    filter(start_end == 'end') %>%   # Filtrar solo los de fin
    pull(nodeID)                     # Obtener IDs
  
  # Asociar a las aristas
  edges = edges %>%                                 # Selesccionar las aristas
    mutate(from = source_nodes, to = target_nodes)  # A?adir columnas Inicio - Fin
  
  # Despu?s de haber agregado los IDs a los nodos de las aristas, 
  # ya no se necesitan los puntos de inicio y fin duplicados. 
  # Despu?s de eliminarlos, se consigue un tibble en el que cada fila representa un nodo ?nico. 
  # Este tibble se puede convertir en un objeto sf con geometr?as POINT.
  
  nodes <- nodes %>%                        # Seleccionar los nodos
    distinct(nodeID, .keep_all = TRUE) %>%  # Individualizar los nodos
    select(-c(edgeID, start_end)) %>%       # Indicar las aristas asociadas
    sf::st_as_sf(coords = c('X', 'Y')) %>%      # Dar geometr?a POINT
    sf::st_set_crs(sf::st_crs(edges))               # "Pegar" los puntos a las aristas
  
  # Lo anterior construy? un objeto sf con geometr?as LINESTRING, que representan las aristas de la red, 
  # y un objeto sf con geometr?as POINT, que representan los nodos de la red. 
  # La funci?n tidygraph::tbl_graph permite convertir estos dos en un objeto tidygraph::tbl_graph. 
  
  final_graph = tidygraph::tbl_graph(nodes = nodes, edges = as_tibble(edges),
                          directed = FALSE, node_key='name')
  return(final_graph)
}

#' Agrega una columna con el ID del componente al que pertenece cada arco.
#' 
#' @param x Un objeto tidygraph.
#' @param field_name Nombre de la columna que almacenara el id del componente.
#' @return Un objeto tidygraph con las el grafo que representa a la red.
#' @export
#' @examples
#' bicycle_igraph %>%
#'  add_components(field_name='id_comp')
add_components = function(x, field_name = 'id_component') {
  # Primero se calcula un vector con subgrafos que contienen los componentes.
  # Luego, se agrega un id por subgrafo a una columna del grafo original (x).

  # Obtiene subgrafos de componentes
  components_list = decompose(x, min.vertices = 2)
  print(paste('[+] Agregando', length(components_list), 'componentes.'))
  
  # Crea la variable que almacenara los ids de los componentes.
  x = x %>%
    activate(edges) %>%
    mutate('{field_name}' := 0)
  
  # Itera sobre cada subgrafo, asociando el componente correspondiente al grafo original x.
  n_component = 1
  for (component_subgraph in components_list) {
    filter_edges_list = get.edge.attribute(component_subgraph)$edgeID
    x = x %>%
      activate(edges) %>%
      mutate('{field_name}' := ifelse(edgeID %in% filter_edges_list, n_component, !!dplyr::sym(field_name)))
    n_component = n_component + 1
  }
  
  return (x)
}

#' Agrega una columna con un 1 si el arco pertenece al diametro, un 0 en caso contrario.
#' 
#' @param x Un objeto tidygraph.
#' @param field_name Nombre de la columna que almacena un 1 si el arco es parte del diametro.
#' @return Un objeto tidygraph con las el grafo que representa a la red.
#' @export
#' @examples
#' bicycle_igraph %>%
#'  add_diameter_of_network(field_name='diameter')
add_diameter_of_network = function(x, field_name='diameter') {
  # Obtiene el subgrafo con el diametro y marca a los arcos que pertenecen
  # al mismo en el grafo original, x.

  # Obtiene el subgrafo con diametro.
  diameter_of_network = get_diameter(x, weights = get.edge.attribute(x, 'weight'), directed=F)
  
  # Obtiene el id de los arcos que pertenecen al diametro, en el grafo original.
  filter_edges_list = x %>%
    activate(nodes) %>%
    filter(get.vertex.attribute(x)$nodeID %in% diameter_of_network) %>%
    activate(edges) %>%
    get.edge.attribute('edgeID')
  
  # Asigna un 1 para los arcos que pertenecen al diametro, y un 0 en otro caso.
  x = x %>%
    activate(edges) %>%
    mutate('{field_name}' := ifelse((edgeID %in% filter_edges_list), 1, 0))
  
  return (x)
}

#' Agrega closeness a los arcos, promediando el valor de closeness de sus vertices.
#' 
#' @param x Un objeto tidygraph.
#' @param field_closeness Nombre de la columna que el valor de closeness para el arco.
#' @param closeness_mode El modo de closeness, en el caso de grafos no dirigidos siempre es all.
#' @return Un objeto tidygraph con las el grafo que representa a la red.
#' @export
#' @examples
#' bicycle_igraph %>%
#'  add_edge_closeness(field_closeness='edge_closeness', closeness_mode="all")
add_edge_closeness = function(x, field_closeness='edge_closeness', closeness_mode="all", local_cutoff=0) {
  # Asigna closeness de cada nodo, luego identifica el valor de closeness de los nodos asociados a cada arco.
  # Finalmente, promedia los valores de closeness de ambos nodos, siende este el valor de closeness del arco.

  # Calcula closeness para cada nodo y lo almacena en el grafo.
  x = x %>%
    activate(nodes) %>%
    mutate(node_closeness = estimate_closeness(., weights = get.edge.attribute(., 'weight'), mode=closeness_mode, cutoff = local_cutoff))
  
  # Obtiene lista de nodos y sus atributos (incluyendo closeness calculado anteriormente).
  x_nodes = x %>%
    activate(nodes) %>%
    as_tibble() %>%
    tibble::rownames_to_column("rowid") %>%
    mutate(rowid = as.integer(rowid))
  
  # Asocia el valor de closeness de los nodos de origen y destino para cada arco.
  # Luego se promedian y se almacenan en la columna {field_closeness}
  x = x %>%
    activate(edges) %>%
    left_join(x_nodes[, c('rowid', 'node_closeness')], by = c('from' = 'rowid'), suffix = c("", "_from")) %>%
    left_join(x_nodes[, c('rowid', 'node_closeness')], by = c('to' = 'rowid'), suffix = c("", "_to")) %>%
    mutate('{field_closeness}' := (node_closeness + node_closeness_to)/2) %>%
    select(-c(node_closeness, node_closeness_to))
  
  return(x)
}

#' Agrega una columna con un 1 si el arco pertenece al diametro del componente correspondiente, un 0 en caso contrario.
#' 
#' @param x Un objeto tidygraph.
#' @param field_components_name Nombre de la columna que ya contiene un ID que segmenta componentes.
#' @param field_diameter_name Nombre de la columna que almacena un 1 si el arco es parte del diametro del componente indicado.
#' @return Un objeto tidygraph con las el grafo que representa a la red.
#' @export
#' @examples
#' bicycle_igraph %>%
#'  add_diameter_of_network_components(field_components_name='component', field_diameter_name='diameter')
add_diameter_of_network_components = function(
  x,
  field_components_name='component',
  field_diameter_name='diameter'
) {
  # Obtiene un subgrafo con el diametro PARA CADA COMPONENTE y marca a los arcos que pertenecen
  # en el grafo original, x.

  # Crea columna en donde se almacenaran los valores 1 y 0.
  x = x %>%
    activate(edges) %>%
    mutate('{field_diameter_name}' := 0)
  
  # Obtiene lista de componentes unicos
  unique_components_id = x %>%
    get.edge.attribute(field_components_name) %>%
    unique()

  # Para cada componente, identifica el subgrafo del diametro, y marca con un 1 a los arcos
  # que pertenecen a este, y con un 0 a los que no pertenecen.
  for (id_component in unique_components_id) {
    component_subgraph = x %>%
      activate(edges) %>%
      filter(get.edge.attribute(., field_components_name) == id_component) %>%
      add_diameter_of_network(field_name='diameter') %>%
      filter(get.edge.attribute(., 'diameter') == 1) %>%
      activate(nodes) %>%
      filter(!node_is_isolated())
    
    filter_edges_list = get.edge.attribute(component_subgraph)$edgeID
    x = x %>%
      activate(edges) %>%
      mutate('{field_diameter_name}' := ifelse(edgeID %in% filter_edges_list, 1, !!dplyr::sym(field_diameter_name)))
  }
  
  return (x)
  
}

#' Agrega una columna a los arcos con el valor de straightness. Esta es calculada como el promedio de
#' straightness en los dos nodos (origen y destino).
#' 
#' @param x Un objeto tidygraph.
#' @param field_straightness Nombre de la columna que almacenara el valor de straightness.
#' @return Un objeto tidygraph con las el grafo que representa a la red.
#' @export
#' @examples
#' bicycle_igraph %>%
#'  add_straightness(field_straightness = 'edge_straightness')
add_straightness = function(x, field_straightness = 'edge_straightness', cutoff=0) {
  # Asigna straightness de cada nodo, luego identifica el valor de straightness de los nodos asociados a cada arco.
  # Finalmente, promedia los valores de straightness de ambos nodos, siende este el valor de straightness del arco.

  # El valor de straightness se calcula obteniendo la distancia euclidiana y ponderada (minima) (por separado), para cada
  # combinacion de pares origen-destino entre nodos. Luego, para cada nodo de origen, se dividen las distancias
  # euclidiana y ponderada, y se promedian (excluyendo 0s y nodos inalcanzables).

  # Asigna un nombre en formato texto a cada nodo, basado en el ID. Esto, porque
  # asi es mas facil identificar los indices de la matriz de distancias euclidianas.
  x = x %>%
    activate(nodes) %>%
    mutate(name = paste('NODE:', nodeID))
  
  # Calcula distancias ponderadas en graph_distances_matrix. Luego calcula las distancias euclidianas en
  # euclidean_distances_matrix y, finalmente, la division entre las distancias euclidianas y ponderadas en distance_rates.
  graph_distances_matrix = x %>%
    distances(weights = get.edge.attribute(., 'weight'))
  
  nodes_geometry = x %>% activate(nodes) %>% pull (geometry)
  euclidean_distances_matrix = sf::st_distance(nodes_geometry, nodes_geometry)
  
  distance_rates = euclidean_distances_matrix/graph_distances_matrix
  
  # Obtiene lista de nodos y asigna el promedio de los valores de distance_rates que tienen como origen cada nodo,
  # excluyendo valores = 0 y NAs (o inalcanzables).
  nodes_list = x %>%
    activate(nodes) %>%
    pull(nodeID)
  
  c_straightness_list = c()
  for (node_id in nodes_list) {
    node_id = paste('NODE:', node_id)

    if (cutoff > 0) {
      cutoff_filter = (as.numeric(distance_rates[node_id,])>0) &
        (as.numeric(graph_distances_matrix[node_id,]) <= cutoff)
    } else {
      cutoff_filter = as.numeric(distance_rates[node_id,])>0
    }

    straightness = mean(distance_rates[node_id,][cutoff_filter], na.rm=T)
    c_straightness_list = c(c_straightness_list, straightness)
  }
  
  # Si x tiene mas de una fila, se asigna el valor de straightness resultante a cada nodo,
  # en la columna node_straightness.
  if (!is.null(c_straightness_list)) {
    x = x %>%
      activate(nodes) %>%
      mutate(node_straightness = c_straightness_list)
  } else {
    x = x %>%
      activate(nodes) %>%
      mutate(node_straightness = 0)
  }
  
  # Finalmente, asigna a cada arco el promedio de straightness de los nodos de origen y destino correspondientes,
  # en unba nueva columna. 
  x_nodes = x %>%
    activate(nodes) %>%
    as_tibble() %>%
    tibble::rownames_to_column("rowid") %>%
    mutate(rowid = as.integer(rowid))

  x = x %>%
    activate(edges) %>%
    left_join(x_nodes[, c('rowid', 'node_straightness')], by = c('from' = 'rowid'), suffix = c("", "_from")) %>%
    left_join(x_nodes[, c('rowid', 'node_straightness')], by = c('to' = 'rowid'), suffix = c("", "_to")) %>%
    mutate('{field_straightness}' := (node_straightness + node_straightness_to)/2) %>%
    select(-c(node_straightness, node_straightness_to))
  
  return (x)
}

#' Crea un tabla resumen de los componentes de un grafo, con metricas representativos para cada uno de ellos.
#' 
#' @param x Un objeto tidygraph.
#' @param field_components_name Nombre de la columna que ya contiene un ID que segmenta componentes.
#' @return Una tabla (Data Frame) con las estadisticas y los indicadores de interes para cada componente.
#' @export
#' @examples
#' bicycle_igraph %>%
#'  calculate_components_attributes(field_components_name='id_comp')
calculate_components_attributes = function(x, field_components_name='component') {
  # Calcula las estadisticas resumen para cada componente dentro del grafo de origen x,
  # asumiendo que los componentes estan en la columna field_components_name, de los arcos.
  # Para ello, recorre cada componente, filtra el grafo en un subgrafo para cada uno y luego
  # calcula las funciones de agregacion pertinentes.

  # Crea una lista con los distintos id para cada componente. 
  unique_components_id = x %>%
    get.edge.attribute(field_components_name) %>%
    unique()
  
  # Genera listas vacias que almacenaran los valores de los distintos indicadores de interes,
  # en forma secuencial.
  id_component_list = c()
  largo_t_list = c()
  largo_prom_list = c()
  beta_index_list = c()
  diametro_list = c()
  c_betweenness_list = c()
  c_closeness_list = c()
  c_straightness_list = c()
  
  for (id_component in unique_components_id) {
    
    print(paste('Procesando subcomponente', id_component))
    
    # Filtro de subgrafo para componente id_component
    component_subgraph = x %>%
      activate(edges) %>%
      filter(get.edge.attribute(., field_components_name) == id_component) %>%
      activate(nodes) %>%
      filter(!node_is_isolated())
    
    # Calculo de largo total de los arcos del subgrafo.
    largo_t = component_subgraph %>%
      get.edge.attribute('weight') %>%
      sum()
    
    # Calculo de largo promedio de los arcos del subgrafo (considerando filtro ci_o_cr == 1).
    largo_prom = component_subgraph %>%
      activate(edges) %>%
      filter(get.edge.attribute(., 'ci_o_cr') == 1) %>%
      activate(nodes) %>%
      filter(!node_is_isolated()) %>%
      get.edge.attribute('weight') %>%
      mean(na.rm=T)
    
    # Calculo de beta index = cantidad de arcos / cantidad de vertices.
    beta_index = length(E(component_subgraph))/length(V(component_subgraph)[inc(E(component_subgraph))])
    
    # Calculo de diametro.
    diametro = diameter(component_subgraph)
    
    # Calculo de promedio de closeness.
    c_closeness = component_subgraph %>%
      activate(edges) %>%
      get.edge.attribute(., 'edge_closeness') %>%
      mean(na.rm=T)
      
    # Calculo de promedio de betweenness.
    c_betweenness = component_subgraph %>%
      activate(edges) %>%
      get.edge.attribute(., 'edge_betweenness') %>%
      mean(na.rm=T)
    
    # Calculo de promedio de straightness.
    c_straightness = component_subgraph %>%
      activate(edges) %>%
      get.edge.attribute(., 'edge_straightness') %>%
      mean(na.rm=T)
    
    # Se anexan los indicadores a las listas creadas antes de las iteraciones.
    id_component_list = rbind(id_component_list, id_component)
    largo_t_list = rbind(largo_t_list, largo_t)
    largo_prom_list = rbind(largo_prom_list, largo_prom)
    beta_index_list = rbind(beta_index_list, beta_index)
    diametro_list = rbind(diametro_list, diametro)
    c_betweenness_list = rbind(c_betweenness_list, c_betweenness)
    c_closeness_list = rbind(c_closeness_list, c_closeness)
    c_straightness_list = rbind(c_straightness_list, c_straightness)
  }
  
  # Se construye el data frame final.
  gi_comp = data.frame(
    id_component=id_component_list,
    largo_t=largo_t_list,
    largo_prom=largo_prom_list,
    beta_index=beta_index_list,
    diametro=diametro_list,
    c_betweenness=c_betweenness_list,
    c_closeness=c_closeness_list,
    c_straightness=c_straightness_list,
    row.names = id_component_list
  )
  
  return (gi_comp)
  
}
