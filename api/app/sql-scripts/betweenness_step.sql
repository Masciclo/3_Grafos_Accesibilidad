-- Run Dijkstra for a single origin node within a specified radius
-- Parameters: network_table, origin_id, radius, edge_weight_column, directed
INSERT INTO {network_table}_betweenness_results (edge_id, flow)
SELECT edge, 1.0 FROM pgr_dijkstra(
    'SELECT id, source, target, {edge_weight_column} AS cost FROM {network_table}',
    {origin_id},
    ARRAY(SELECT id FROM {network_table}_vertices_pgr v 
          WHERE ST_DWithin(v.the_geom, (SELECT the_geom FROM {network_table}_vertices_pgr WHERE id = {origin_id}), {radius})),
    directed := {directed}
)
WHERE edge != -1;
