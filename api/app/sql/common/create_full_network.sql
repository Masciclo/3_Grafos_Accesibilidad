-- create_full_network.sql
-- Description: Merges OSM road network and cycleway shapefiles.
-- Performance: Optimized with temp tables, GiST indexes, and ST_Node to planarize crossings.
-- Deduplication: Keeps original cycleways and streets separate without duplicate overlap or proximity-based hierarchy shifts.

DROP TABLE IF EXISTS {result_name} CASCADE;

-- 1. Extract raw cycleway geometries
DROP TABLE IF EXISTS temp_raw_cycleways;
CREATE TEMP TABLE temp_raw_cycleways AS
SELECT 
    (ST_Dump(ST_MakeValid(geometry))).geom as geometry,
    {bike_impedance}::float as impedance,
    'cycleway'::text as highway,
    'cycleway'::text as original_highway,
    FALSE as is_project,
    NULL::text as project_id,
    NULL::integer as parent_baseline_id
FROM {ciclo}
WHERE geometry IS NOT NULL
{filters}
{projects_union};
CREATE INDEX temp_raw_cycleways_gix ON temp_raw_cycleways USING GIST (geometry);
ANALYZE temp_raw_cycleways;

-- 2. Nodalize (Planarize) crossing lines in the entire network
DROP TABLE IF EXISTS temp_nodalized_lines;
CREATE TEMP TABLE temp_nodalized_lines AS
SELECT (ST_Dump(ST_Node(ST_Collect(geometry)))).geom as geometry
FROM (
    SELECT geometry FROM temp_raw_cycleways
    UNION ALL
    SELECT geometry FROM {osm} WHERE geometry IS NOT NULL
) t;

CREATE INDEX temp_nodalized_lines_gix ON temp_nodalized_lines USING GIST (geometry);
ANALYZE temp_nodalized_lines;

-- 3. Match back attributes using precise Centroid ST_DWithin (0.2m tolerance to absorb float rounding errors)
DROP TABLE IF EXISTS matched_all;
CREATE TEMP TABLE matched_all AS
SELECT DISTINCT ON (ST_AsBinary(n.geometry)) 
    n.geometry,
    COALESCE(
        CASE 
            WHEN c.geometry IS NOT NULL THEN c.impedance
            ELSE o.impedance
        END,
        1.0
    )::float as impedance,
    COALESCE(
        CASE 
            WHEN c.geometry IS NOT NULL THEN 'cycleway'::text
            ELSE o.highway::text
        END,
        'residential'::text
    )::text as highway,
    COALESCE(
        CASE 
            WHEN c.geometry IS NOT NULL THEN 'cycleway'::text
            ELSE o.highway::text
        END,
        'residential'::text
    )::text as original_highway,
    CASE 
        WHEN c.geometry IS NOT NULL THEN c.is_project
        ELSE COALESCE(o.is_project, FALSE)
    END as is_project,
    CASE 
        WHEN c.geometry IS NOT NULL THEN c.project_id
        ELSE o.project_id::text
    END as project_id,
    CASE 
        WHEN c.geometry IS NOT NULL THEN c.parent_baseline_id::integer
        ELSE o.parent_baseline_id::integer
    END as parent_baseline_id
FROM temp_nodalized_lines n
LEFT JOIN temp_raw_cycleways c ON ST_DWithin(ST_LineInterpolatePoint(n.geometry, 0.5), c.geometry, 0.20)
LEFT JOIN {osm} o ON ST_DWithin(ST_LineInterpolatePoint(n.geometry, 0.5), o.geometry, 0.20)
ORDER BY ST_AsBinary(n.geometry), (c.geometry IS NOT NULL) DESC;

-- 4. Create output network table (explicitly ordered to ensure 100% deterministic SERIAL primary keys across runs)
CREATE TABLE {result_name} AS
SELECT * FROM matched_all
ORDER BY ST_AsBinary(geometry);


-- Standard pgRouting columns
ALTER TABLE {result_name} ADD COLUMN id SERIAL PRIMARY KEY;
ALTER TABLE {result_name} ADD COLUMN source integer;
ALTER TABLE {result_name} ADD COLUMN target integer;
ALTER TABLE {result_name} ADD COLUMN length float;
ALTER TABLE {result_name} ADD COLUMN cost float;

UPDATE {result_name} SET length = ST_Length(geometry);
UPDATE {result_name} SET cost = ST_Length(geometry) * impedance;

CREATE INDEX IF NOT EXISTS {result_name}_geom_idx 
ON {result_name}
USING GIST (geometry);
