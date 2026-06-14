-- create_routing_topology.sql
-- Description: Standard pgRouting topology creation.
-- Optimized for metropolitan scale using pre-flight indexing and VACUUM.

-- 1. Ensure columns exist
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS source integer;
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS target integer;

-- 2. Build spatial index (Critical)
CREATE INDEX IF NOT EXISTS {table}_geom_idx ON {table} USING GIST (geometry);

-- 3. Maintenance (Ensures the planner knows the data distribution)
ANALYZE {table};

-- 4. Execute Topology
-- Parameterized tolerance (defaults to 0.0001)
SELECT pgr_createTopology('{table}', {tolerance}, 'geometry', 'id');

-- 4.1. Populate X/Y for A* Heuristic (Now that vertices table exists)
ALTER TABLE {table}_vertices_pgr ADD COLUMN IF NOT EXISTS x float8;
ALTER TABLE {table}_vertices_pgr ADD COLUMN IF NOT EXISTS y float8;
UPDATE {table}_vertices_pgr SET x = ST_X(the_geom), y = ST_Y(the_geom);

-- 4.2. Denormalize coordinates into edge table for high-speed A*
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS x1 float8;
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS y1 float8;
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS x2 float8;
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS y2 float8;

UPDATE {table} t 
SET x1 = v1.x, y1 = v1.y, x2 = v2.x, y2 = v2.y
FROM {table}_vertices_pgr v1, {table}_vertices_pgr v2
WHERE t.source = v1.id AND t.target = v2.id;

-- 5. Final Graph Indexes
CREATE INDEX IF NOT EXISTS {table}_source_idx ON {table} (source);
CREATE INDEX IF NOT EXISTS {table}_target_idx ON {table} (target);
ANALYZE {table};
