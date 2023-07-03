DROP TABLE IF EXISTS {result_name};

CREATE TABLE {result_name} AS 
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
	{osm} AS b
WHERE
	ST_GeometryType(geometry) IN ('ST_LineString', 'ST_MultiLineString');

ALTER TABLE {result_name} ADD COLUMN id SERIAL PRIMARY KEY;

CREATE INDEX IF NOT EXISTS geom_idx 
ON {result_name}
USING GIST (geometry);