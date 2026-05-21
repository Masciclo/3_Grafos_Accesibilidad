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
    -- DEDUPLICATION LOGIC:
    -- Take road segments only if they are NOT redundant with a project geometry.
    -- Redundancy = Within 0.5 meters AND > 80% linear overlap.
    SELECT
        (ST_Dump(ST_MakeValid(b.geometry))).geom as geometry,
        b.impedance as impedance,
        b.highway as highway,
        b.is_project as is_project
    FROM
        {osm} AS b
    WHERE NOT EXISTS (
        SELECT 1 FROM cycleway_geoms c 
        WHERE ST_DWithin(b.geometry, c.geometry, 0.5)
          AND ST_Length(ST_Intersection(b.geometry, ST_Buffer(c.geometry, 0.5))) / NULLIF(ST_Length(b.geometry), 0) > 0.8
    )
),
dumped_geoms AS (
    SELECT * FROM cycleway_geoms
    UNION ALL
    SELECT * FROM osm_filtered
),
normalized_geoms AS (
    -- FINAL DEDUPLICATION: Handle reversed OSM duplicates (e.g. 764 vs 765)
    -- We force all lines to follow a deterministic vertex order
    SELECT DISTINCT ON (
        CASE 
            WHEN ST_StartPoint(geometry) < ST_EndPoint(geometry) THEN ST_AsBinary(geometry)
            ELSE ST_AsBinary(ST_Reverse(geometry))
        END
    )
    geometry,
    -- Case: If it is a project, force the low impedance. Otherwise keep road penalty.
    CASE 
        WHEN is_project = TRUE THEN {bike_impedance} 
        ELSE impedance 
    END as impedance,
    highway,
    is_project
    FROM dumped_geoms
    WHERE geometry IS NOT NULL 
      AND ST_GeometryType(geometry) = 'ST_LineString'
      AND ST_Length(geometry) > 0.0001
    ORDER BY 
        CASE 
            WHEN ST_StartPoint(geometry) < ST_EndPoint(geometry) THEN ST_AsBinary(geometry)
            ELSE ST_AsBinary(ST_Reverse(geometry))
        END,
        is_project DESC, -- Favor project version if both exist
        impedance ASC    -- Favor lower cost if duplicates remain
)
SELECT * FROM normalized_geoms;

ALTER TABLE {result_name} ADD COLUMN id SERIAL PRIMARY KEY;
ALTER TABLE {result_name} ADD COLUMN length float;
ALTER TABLE {result_name} ADD COLUMN cost float;

UPDATE {result_name} SET length = ST_Length(geometry);
UPDATE {result_name} SET cost = ST_Length(geometry) * impedance;

CREATE INDEX IF NOT EXISTS {result_name}_geom_idx 
ON {result_name}
USING GIST (geometry);
