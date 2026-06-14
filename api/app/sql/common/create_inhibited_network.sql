-- 1. Segments INSIDE the danger zone (Intersections)
-- We use DISTINCT ON geometry to ensure a segment only inherits ONE impedance (the highest) if it touches multiple buffers.
DROP TABLE IF EXISTS network_with_impedance;
CREATE TEMP TABLE network_with_impedance AS
SELECT DISTINCT ON (geom_dump)
    (ST_Dump(ST_MakeValid(ST_Intersection(a.geometry, b.geometry)))).geom AS geom_dump,
    CASE 
        WHEN a.is_project = TRUE THEN a.impedance -- PRESERVE PROJECT INCENTIVE
        ELSE b.impedance 
    END as impedance,
    a.highway,
    COALESCE(a.is_project, FALSE) as is_project,
    a.project_id,
    a.parent_baseline_id
FROM 
    {network_table} a
    INNER JOIN buffers.{impedance_buffer} b 
    ON a.geometry && b.geometry AND ST_Intersects(a.geometry, b.geometry);

-- 2. Segments OUTSIDE the danger zone (Safe parts of the street)
-- STRATEGY: Instead of one global ST_Union, we subtract the localized union of buffers 
-- that actually touch the segment. This is much more memory efficient.
DROP TABLE IF EXISTS network_without_impedance;
CREATE TEMP TABLE network_without_impedance AS
SELECT
    (ST_Dump(ST_MakeValid(ST_Difference(a.geometry, diff.total_buffer)))).geom AS geom_dump,
    CASE 
        WHEN a.is_project = TRUE THEN a.impedance -- PRESERVE PROJECT INCENTIVE
        ELSE 1.0 
    END as impedance,
    a.highway,
    COALESCE(a.is_project, FALSE) as is_project,
    a.project_id,
    a.parent_baseline_id
FROM
    {network_table} a,
    LATERAL (
        SELECT ST_Union(b.geometry) as total_buffer
        FROM buffers.{impedance_buffer} b
        WHERE a.geometry && b.geometry AND ST_Intersects(a.geometry, b.geometry)
    ) diff
WHERE diff.total_buffer IS NOT NULL;

-- 2.1 ADDITION: Segments that don't touch ANY buffer (Purely safe streets)
INSERT INTO network_without_impedance
SELECT 
    geometry as geom_dump,
    CASE 
        WHEN is_project = TRUE THEN impedance -- PRESERVE PROJECT INCENTIVE
        ELSE 1.0 
    END as impedance,
    highway,
    COALESCE(is_project, FALSE) as is_project,
    project_id,
    parent_baseline_id
FROM {network_table} a
WHERE NOT EXISTS (
    SELECT 1 FROM buffers.{impedance_buffer} b WHERE a.geometry && b.geometry AND ST_Intersects(a.geometry, b.geometry)
);

-- 3. Final Consolidation (The Union of fragmented city parts)
DROP TABLE IF EXISTS {result_name};
CREATE TABLE {result_name} AS
SELECT DISTINCT ON (geometry) -- FINAL GUARD against overlapping fragments
    geom_dump as geometry,
    impedance,
    highway,
    is_project,
    project_id,
    parent_baseline_id
FROM (
    SELECT * FROM network_with_impedance
    UNION ALL
    SELECT * FROM network_without_impedance
) sub
WHERE ST_GeometryType(geom_dump) = 'ST_LineString'
  AND ST_Length(geom_dump) > 0.0001
ORDER BY geometry, impedance DESC; -- Keep highest impedance if duplicates remain

CREATE INDEX {result_name}_gix ON {result_name} USING GIST (geometry);
