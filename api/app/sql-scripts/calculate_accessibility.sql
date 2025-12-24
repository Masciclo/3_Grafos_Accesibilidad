ALTER TABLE {h3_table_name} 
ADD COLUMN centroid GEOMETRY(POINT, {srid});

UPDATE {h3_table_name}
SET centroid = ST_Centroid(geometry);

ALTER TABLE {h3_table_name} 
ADD COLUMN nearest_node_id INTEGER;

CREATE INDEX node_geom_idx ON {node_table} USING gist(geom);

UPDATE {h3_table_name} AS h
SET nearest_node_id = 
(
    SELECT node_id FROM {node_table} AS n
    WHERE ST_DWithin(h.centroid, n.geom, {radius})
    ORDER BY h.centroid <-> n.geom ASC
    LIMIT 1
);

ALTER TABLE {h3_table_name} 
ADD COLUMN accessibility FLOAT;

drop table if exists temp_table;
CREATE temp TABLE temp_table AS
WITH impedance_table AS
(
	SELECT (GetTopoGeomElements(topogeom))[1] AS edge_data_id, impedance
	FROM {table_name} 
)
SELECT
	distinct
    ed.edge_id AS id,
    ed.start_node AS source,
    ed.end_node AS target,
    ST_Length(ed.geom)*it.impedance AS cost,
    ed.geom as the_geom
FROM
    {topo_name}.edge_data AS ed
left JOIN impedance_table AS it ON ed.edge_id = it.edge_data_id;

UPDATE {h3_table_name} AS h1
SET accessibility = 
(
    SELECT SUM(cost) FROM
    (
        SELECT cost FROM pgr_dijkstra(
        'SELECT id, source, target, cost FROM temp_table',
        h1.nearest_node_id,
        ARRAY(SELECT nearest_node_id FROM {h3_table_name} WHERE nearest_node_id IS NOT NULL),
        directed := false
        ) AS routes
    ) AS total_cost
);

