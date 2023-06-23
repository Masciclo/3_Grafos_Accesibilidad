DROP TABLE IF EXISTS {result_name};

CREATE TABLE {result_name} AS 
SELECT a.geometry as geometry FROM {ciclo} AS a 
UNION ALL
SELECT b.geometry as geometry FROM {osm} AS b;

ALTER TABLE {result_name} ADD COLUMN id SERIAL PRIMARY KEY;