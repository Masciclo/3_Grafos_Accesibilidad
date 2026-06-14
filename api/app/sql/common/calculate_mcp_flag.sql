-- calculate_mcp_flag.sql
-- Phase 13: Calculates the "Maximum Common Polygon" (MCP) flag for the final layers.
-- Using TEMP TABLE for cross-statement persistence.

-- 1. Create the MCP boundary (Exact Union of EOD Zones)
CREATE TEMP TABLE temp_mcp_boundary AS
SELECT ST_Union(geometry) as boundary FROM {zones_table};

-- 2. Update the Flag in the Master Network Table
UPDATE {scenario_prefix}_network n
SET participating_in_analysis = ST_Intersects(n.geometry, (SELECT boundary FROM temp_mcp_boundary))
WHERE EXISTS (SELECT 1 FROM temp_mcp_boundary);

-- 3. Update the Flag in the Master H3 Table
UPDATE {scenario_prefix}_h3 h
SET participating_in_analysis = ST_Intersects(ST_Centroid(h.geometry), (SELECT boundary FROM temp_mcp_boundary))
WHERE EXISTS (SELECT 1 FROM temp_mcp_boundary);

-- Cleanup
DROP TABLE temp_mcp_boundary;
