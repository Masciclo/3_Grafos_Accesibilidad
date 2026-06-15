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
    -- DEDUPLICATION LOGIC OPTIMIZED:
    -- Use BBOX operator (&&) to leverage spatial index.
    -- Use a simpler distance check to skip heavy ST_Intersection/ST_Buffer.
    SELECT
        (ST_Dump(ST_MakeValid(b.geometry))).geom as geometry,
        b.impedance as impedance,
        b.highway as highway,
        b.is_project as is_project,
        b.project_id as project_id,
        b.parent_baseline_id as parent_baseline_id
    FROM
        {osm} AS b
    WHERE b.is_project = TRUE -- NEVER filter out projects, they represent the sovereign state
       OR NOT EXISTS (
        SELECT 1 FROM cycleway_geoms c 
        WHERE b.geometry && ST_Expand(c.geometry, 0.5) -- BBOX Filter First
          AND ST_DWithin(b.geometry, c.geometry, 0.5) -- Fast distance check
    )
),
dumped_geoms AS (
    SELECT 
        geometry, 
        impedance, 
        highway, 
        is_project,
        NULL::text as project_id,
        NULL::integer as parent_baseline_id
    FROM cycleway_geoms
    UNION ALL
    SELECT 
        geometry, 
        impedance, 
        highway, 
        is_project,
        project_id::text as project_id,
        parent_baseline_id::integer as parent_baseline_id
    FROM osm_filtered
),
normalized_geoms AS (
    -- FINAL DEDUPLICATION: Handle reversed OSM duplicates
    -- Use MD5 Hash of the binary geometry for ultra-fast comparison
    SELECT DISTINCT ON (
        MD5(ST_AsBinary(
            CASE 
                WHEN ST_StartPoint(geometry) < ST_EndPoint(geometry) THEN geometry
                ELSE ST_Reverse(geometry)
            END
        ))
    )
    geometry,
    -- PROTECT SOVEREIGN IMPEDANCE: 
    -- If it's a project, keep its assigned impedance (Strictly 0.5 for +Ciclo).
    CASE 
        WHEN is_project = TRUE THEN 0.5
        WHEN highway = 'cycleway' THEN {bike_impedance}
        ELSE impedance 
    END as impedance,
    highway,
    is_project,
    project_id,
    parent_baseline_id
    FROM dumped_geoms
    WHERE geometry IS NOT NULL 
      AND ST_GeometryType(geometry) = 'ST_LineString'
      AND ST_Length(geometry) > 0.0001
    ORDER BY 
        MD5(ST_AsBinary(
            CASE 
                WHEN ST_StartPoint(geometry) < ST_EndPoint(geometry) THEN geometry
                ELSE ST_Reverse(geometry)
            END
        )), 
        impedance DESC
)
SELECT * FROM normalized_geoms;

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
