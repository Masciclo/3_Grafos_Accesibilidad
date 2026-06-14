-- prune_h3_to_mcp.sql
-- Phase 13: 'Cookie Cutter' Pruning
-- Physically removes H3 cells whose centroids fall outside the EOD Zonification.

-- 1. Create the MCP boundary (Exact Union of EOD Zones)
-- Since we are now using conventional ingestion, we know the source zones table
CREATE TEMP TABLE temp_mcp_boundary AS
SELECT ST_Union(geometry) as boundary FROM {zones_table};

-- 2. Prune the H3 table
-- Anchor to Centroid to prevent 'jagged' edges while matching the survey intent
DELETE FROM {h3_table}
WHERE NOT ST_Intersects(ST_Centroid(geometry), (SELECT boundary FROM temp_mcp_boundary))
OR geometry IS NULL;

-- Cleanup
DROP TABLE temp_mcp_boundary;
