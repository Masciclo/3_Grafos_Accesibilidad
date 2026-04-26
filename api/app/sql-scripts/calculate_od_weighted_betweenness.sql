-- Calculate OD-Weighted Betweenness Centrality
-- 1. Identify Nearest Nodes for each OD Zone Centroid
DROP TABLE IF EXISTS {location_prefix}_zone_nodes;
CREATE TABLE {location_prefix}_zone_nodes AS
WITH zone_centroids AS (
    SELECT 
        "ZONA" as zone_id, 
        ST_Centroid(geometry) as geom
    FROM {od_zones_table}
)
SELECT 
    zc.zone_id,
    (
        SELECT n.id 
        FROM {topo_name}.node n 
        ORDER BY n.the_geom <-> zc.geom 
        LIMIT 1
    ) as node_id
FROM zone_centroids zc;

-- 2. Calculate Shortest Paths weighted by OD Flow
DROP TABLE IF EXISTS {location_prefix}_od_weighted_betweenness;
CREATE TABLE {location_prefix}_od_weighted_betweenness AS
WITH od_pairs AS (
    SELECT 
        zn_o.node_id as source_node,
        zn_d.node_id as target_node,
        m."Viajes_Totales" as flow
    FROM {od_matrix_table} m
    JOIN {location_prefix}_zone_nodes zn_o ON m."Zona_Origen"::text = zn_o.zone_id::text
    JOIN {location_prefix}_zone_nodes zn_d ON m."Zona_Destino"::text = zn_d.zone_id::text
    WHERE m."Viajes_Totales" > 0 
      AND zn_o.node_id != zn_d.node_id
),
paths AS (
    SELECT 
        r.edge,
        od.flow
    FROM od_pairs od,
    LATERAL pgr_dijkstra(
        'SELECT id, source, target, cost FROM ' || quote_ident('{network_table}'),
        od.source_node,
        od.target_node,
        directed := false
    ) r
    WHERE r.edge != -1
)
SELECT 
    edge as edge_id,
    sum(flow) as total_flow
FROM paths
GROUP BY edge;

-- 3. Update the network table with the calculated flow
ALTER TABLE {network_table} ADD COLUMN IF NOT EXISTS od_flow double precision;
UPDATE {network_table} n
SET od_flow = COALESCE(w.total_flow, 0)
FROM {location_prefix}_od_weighted_betweenness w
WHERE n.id = w.edge_id;
