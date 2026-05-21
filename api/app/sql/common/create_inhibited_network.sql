-- Consolidated Buffer for Difference (The entire danger zone as one geometry)
DROP TABLE IF EXISTS total_inhib_buffer;
CREATE TEMP TABLE total_inhib_buffer AS
SELECT ST_Union(geometry) as geometry FROM buffers.{inhib_buffer};

-- 1. Segments INSIDE the danger zone (Intersections)
-- We use DISTINCT ON geometry to ensure a segment only inherits ONE impedance (the highest) if it touches multiple buffers.
DROP TABLE IF EXISTS network_with_impedance;
CREATE TEMP TABLE network_with_impedance AS
SELECT DISTINCT ON (geom_dump)
    (ST_Dump(ST_MakeValid(ST_Intersection(a.geometry, b.geometry)))).geom AS geom_dump,
    b.impedance AS impedance,
    a.highway,
    COALESCE(a.is_project, FALSE) as is_project
FROM 
    {network_table} a
    INNER JOIN buffers.{impedance_buffer} b 
    ON ST_Intersects(a.geometry, b.geometry);

-- 2. Segments OUTSIDE the danger zone (Safe parts of the street)
-- FIXED: We use a LEFT JOIN / WHERE logic to ensure we only process segments once against the unioned buffer.
DROP TABLE IF EXISTS network_without_impedance;
CREATE TEMP TABLE network_without_impedance AS
SELECT
    (ST_Dump(ST_MakeValid(ST_Difference(a.geometry, b.geometry)))).geom AS geom_dump,
    1.0 as impedance,
    a.highway,
    COALESCE(a.is_project, FALSE) as is_project
FROM
    {network_table} a
CROSS JOIN 
    total_inhib_buffer b
WHERE ST_Intersects(a.geometry, b.geometry);

-- 2.1 ADDITION: Segments that don't touch ANY buffer (Purely safe streets)
INSERT INTO network_without_impedance
SELECT 
    geometry as geom_dump,
    1.0 as impedance,
    highway,
    COALESCE(is_project, FALSE) as is_project
FROM {network_table} a
WHERE NOT EXISTS (
    SELECT 1 FROM total_inhib_buffer b WHERE ST_Intersects(a.geometry, b.geometry)
);

-- 3. Final Consolidation (The Union of fragmented city parts)
DROP TABLE IF EXISTS {result_name};
CREATE TABLE {result_name} AS
SELECT DISTINCT ON (geometry) -- FINAL GUARD against overlapping fragments
    geom_dump as geometry,
    impedance,
    highway,
    is_project
FROM (
    SELECT * FROM network_with_impedance
    UNION ALL
    SELECT * FROM network_without_impedance
) sub
WHERE geom_dump IS NOT NULL 
  AND ST_GeometryType(geom_dump) = 'ST_LineString'
  AND ST_Length(geom_dump) > 0.0001
ORDER BY geometry, impedance DESC; -- Keep highest impedance if duplicates remain

CREATE INDEX {result_name}_gix ON {result_name} USING GIST (geometry);
