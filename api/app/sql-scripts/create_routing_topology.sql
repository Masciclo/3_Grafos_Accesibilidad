-- Create routing topology for pgRouting
-- This script populates the source and target columns by snapping geometries

-- 1. Add source and target columns if they do not exist
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS source integer;
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS target integer;

-- 2. Create the topology
-- table_name, tolerance, geometry_column, id_column
SELECT pgr_createTopology('{table}', 1.0, 'geometry', 'id');

-- 3. Recalculate length and cost for segments (in case topology creation split any lines)
UPDATE {table} SET length = ST_Length(geometry);
UPDATE {table} SET cost = ST_Length(geometry) * impedance;

-- 4. Analyze the graph to ensure it's ready
SELECT pgr_analyzeGraph('{table}', 1.0, 'geometry', 'id');
