DROP TABLE IF EXISTS {result_name};

CREATE TABLE {result_name} AS 
WITH cycleway_geoms AS (
    SELECT
        (ST_Dump(ST_MakeValid(a.geometry))).geom as geometry,
        {bike_impedance} as impedance,
        'cycleway' as highway,
        FALSE as is_project
    FROM
        {ciclo} AS a
    WHERE 1=1 
    {filters}
),
osm_filtered AS (
    -- Take only roads that are NOT identical to a cycleway
    -- This prevents the "Double Stack" duplication
    SELECT
        (ST_Dump(ST_MakeValid(b.geometry))).geom as geometry,
        b.impedance as impedance,
        b.highway as highway,
        b.is_project as is_project
    FROM
        {osm} AS b
    WHERE NOT EXISTS (
        SELECT 1 FROM cycleway_geoms c 
        WHERE ST_Equals(b.geometry, c.geometry)
    )
),
dumped_geoms AS (
    SELECT * FROM cycleway_geoms
    UNION ALL
    SELECT * FROM osm_filtered
)
SELECT 
    geometry,
    impedance,
    highway,
    is_project
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
