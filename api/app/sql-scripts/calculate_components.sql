-- FOR COMPONENTS
drop table if exists {result_table};
CREATE TABLE {result_table} AS
WITH impedance_table AS
(
	SELECT (GetTopoGeomElements(topogeom))[1] AS edge_data_id, impedance
	FROM {table_name} 
	where impedance <= 1
)
SELECT
	distinct
    ed.edge_id AS id,
    ed.start_node AS source,
    ed.end_node AS target,
    ST_Length(ed.geom) AS len,
	it.impedance,
    ed.geom as the_geom,
    0 AS component 
FROM
    {topo_name}.edge_data AS ed
left JOIN impedance_table AS it ON ed.edge_id = it.edge_data_id
where impedance <= 1;
	
drop table if exists components_table;
create temp table components_table as
select * from pgr_connectedComponents(
    'SELECT id, source, target, len as cost FROM {result_table}'
);

UPDATE {result_table}
SET component = components_table.component
FROM components_table
WHERE {result_table}.source = components_table.node;