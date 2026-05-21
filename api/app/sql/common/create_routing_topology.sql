-- Create routing topology for pgRouting
-- This script populates the source and target columns by snapping geometries

-- 1. Add ID, source, target, length and cost columns if they do not exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='{table}' AND column_name='id') THEN
        ALTER TABLE {table} ADD COLUMN id SERIAL PRIMARY KEY;
    END IF;
END $$;

ALTER TABLE {table} ADD COLUMN IF NOT EXISTS source integer;
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS target integer;
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS length float;
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS cost float;

-- 2. Create the topology
-- table_name, tolerance, geometry_column, id_column
SELECT pgr_createTopology('{table}', 1.0, 'geometry', 'id');

-- 3. Recalculate length and cost for segments
UPDATE {table} SET length = ST_Length(geometry);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='{table}' AND column_name='impedance') THEN
        UPDATE {table} SET cost = ST_Length(geometry) * impedance;
    ELSE
        UPDATE {table} SET cost = ST_Length(geometry);
    END IF;
END $$;

-- 4. Analyze the graph to ensure it's ready
SELECT pgr_analyzeGraph('{table}', 1.0, 'geometry', 'id');
