CREATE TABLE {table_name}_results AS
SELECT
    edge_id AS id,
    start_node AS source,
    end_node AS target,
    ST_Length(geom) AS cost,
    geom as the_geom,
    0 AS component 
FROM
    {topo}.edge_data;

-- Crear una tabla con los componentes
DROP TABLE IF EXISTS components_result;
CREATE TABLE components_result AS
SELECT * FROM pgr_connectedComponents(
    'SELECT id, source, target, cost FROM {table_name}_results'
);

-- Actualizar la tabla de red con la información de los componentes
UPDATE {table_name}_results
SET component = components_result.component
FROM components_result
WHERE {table_name}_results.source = components_result.node;

DROP TABLE components_result;
