DROP TABLE IF EXISTS {result_name};

CREATE TABLE {result_name} AS 
SELECT a.geometry as the_geom FROM {ciclo} AS a 
UNION ALL
SELECT b.geometry as the_geom FROM {osm} AS b;
