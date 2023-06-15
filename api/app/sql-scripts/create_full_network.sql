CREATE TABLE {result_name} AS SELECT ST_Union(a.geom, b.geom) as union_geometry 
FROM {ciclo} AS a, {osm} AS b 
WHERE ST_Intersects(a.geom, b.geom)