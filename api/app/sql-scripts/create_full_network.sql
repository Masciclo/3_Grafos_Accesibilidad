DROP TABLE IF EXISTS {result_name};

CREATE TABLE {result_name} AS 
WITH dumped_geoms AS (
    SELECT
        (ST_Dump(ST_MakeValid(a.geometry))).geom as geometry,
        0.8 as impedance 
    FROM
        {ciclo} AS a
    WHERE 1=1 
    {filters}
    UNION ALL
    SELECT
        (ST_Dump(ST_MakeValid(b.geometry))).geom as geometry,
        impedance as impedance
    FROM
        {osm} AS b
)
SELECT 
    geometry,
    impedance
FROM dumped_geoms
WHERE geometry IS NOT NULL 
  AND ST_GeometryType(geometry) = 'ST_LineString'
  AND ST_Length(geometry) > 0.0001;

ALTER TABLE {result_name} ADD COLUMN id SERIAL PRIMARY KEY;
ALTER TABLE {result_name} ADD COLUMN length float;
ALTER TABLE {result_name} ADD COLUMN cost float;

UPDATE {result_name} SET length = ST_Length(geometry);
UPDATE {result_name} SET cost = ST_Length(geometry) * impedance;

CREATE INDEX IF NOT EXISTS {result_name}_geom_idx 
ON {result_name}
USING GIST (geometry);
