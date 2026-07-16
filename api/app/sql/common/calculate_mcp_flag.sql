-- calculate_mcp_flag.sql
-- Phase 13: Calculates the "Maximum Common Polygon" (MCP) flag for the final layers.

-- 1. Update the Flag in the Master Network Table using subquery lookup
UPDATE {scenario_prefix}_network n
SET participating_in_analysis = EXISTS (
    SELECT 1 
    FROM {zones_table} z 
    WHERE ST_Intersects(n.geometry, z.geometry)
);

-- 2. Update the Flag in the Master H3 Table using subquery lookup
UPDATE {scenario_prefix}_h3 h
SET participating_in_analysis = EXISTS (
    SELECT 1 
    FROM {zones_table} z 
    WHERE ST_Intersects(ST_Centroid(h.geometry), z.geometry)
);
