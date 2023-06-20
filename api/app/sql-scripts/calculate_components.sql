CREATE TABLE input_connectedComponents AS
SELECT
    edge_id AS id,
    start_node AS source,
    end_node AS target,
    ST_Length(geom) AS cost,
	geom as the_geom
FROM
    {topo}.edge_data;

-- Crear una tabla con los componentes
DROP TABLE IF EXISTS {components_table};
CREATE TABLE {components_table} AS
SELECT * FROM pgr_connectedComponents(
    'SELECT id, source, target, cost FROM input_connectedComponents'
);

DROP TABLE input_connectedComponents;
