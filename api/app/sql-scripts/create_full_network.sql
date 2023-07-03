DROP TABLE IF EXISTS {table_name}_full_network;

CREATE TABLE {table_name}_full_network AS 
SELECT
	a.geometry as geometry,
	0.8 as impedance 
FROM
	{ciclo} AS a
{filters};
UNION ALL
SELECT
	b.geometry as geometry,
	impedance as impedance
FROM
	{inhibited_network} AS b
WHERE
	ST_GeometryType(geometry) IN ('ST_LineString', 'ST_MultiLineString');

ALTER TABLE {table_name}_full_network ADD COLUMN id SERIAL PRIMARY KEY;

CREATE INDEX IF NOT EXISTS geom_idx 
ON {table_name}_full_network
USING GIST (geometry);