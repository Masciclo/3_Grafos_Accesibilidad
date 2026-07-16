-- prune_h3_to_mcp.sql
-- Phase 13: 'Cookie Cutter' Pruning
-- Physically removes H3 cells whose centroids fall outside the EOD Zonification.

-- 1. Prune the H3 table using spatial index lookup against the zones
-- Anchor to Centroid to prevent 'jagged' edges while matching the survey intent
DELETE FROM {h3_table}
WHERE NOT EXISTS (
    SELECT 1 
    FROM {zones_table} z 
    WHERE ST_Intersects(ST_Centroid({h3_table}.geometry), z.geometry)
)
OR geometry IS NULL;
