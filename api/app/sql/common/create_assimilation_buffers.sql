-- create_assimilation_buffers.sql
-- Task 18.1: Generates influence zones for Topological Refactoring.
-- Parameters: result_table, projects_table, mr_distance (Magnetismo a Referencia)

-- 1. Create a clean buffer around project geometries
DROP TABLE IF EXISTS {result_table};
CREATE TABLE {result_table} AS
SELECT 
    id as project_id,
    ST_Union(ST_Buffer(geometry, {mr_distance})) as geometry
FROM {projects_table}
GROUP BY id;

-- 2. Create GIST Index for high-performance planar intersection
CREATE INDEX {result_table}_gix ON {result_table} USING GIST (geometry);

-- 3. Audit Result
DO $$
BEGIN
    RAISE NOTICE 'Assimilation buffers created for % projects using MR=%m', 
        (SELECT COUNT(*) FROM {result_table}), {mr_distance};
END $$;
