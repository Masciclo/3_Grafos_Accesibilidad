DROP TABLE IF EXISTS {result_name};

CREATE TABLE {result_name} AS 
SELECT ST_Union(a.geometry, b.geometry) as union_geometry 
FROM {ciclo} AS a, {osm} AS b 
WHERE ST_Intersects(a.geometry, b.geometry);