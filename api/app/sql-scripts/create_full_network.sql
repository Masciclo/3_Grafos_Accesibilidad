DROP TABLE IF EXISTS {result_name};

CREATE TABLE {result_name} AS 
SELECT ST_Union(ST_GeomFromText(a.geometry, 32719), ST_GeomFromText(b.geometry, 32719)) as union_geometry 
FROM {ciclo} AS a, {osm} AS b 
WHERE ST_Intersects(ST_GeomFromText(a.geometry, 32719), ST_GeomFromText(b.geometry, 32719));