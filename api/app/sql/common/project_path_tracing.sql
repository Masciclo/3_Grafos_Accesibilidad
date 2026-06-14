-- project_path_tracing.sql
-- Description: Identifies OD pairs that intersect with specific projects and counts unique travelers.
-- Parameters: routing_results_table, network_table, result_table

DROP TABLE IF EXISTS {result_table};
CREATE TABLE {result_table} AS
SELECT 
    p.project_id,
    COUNT(DISTINCT od.pair_id) as total_unique_travelers
FROM {network_table} p
JOIN {routing_results_table} od 
    ON p.geometry && od.geometry -- GIST BBOX Filter
    AND ST_Intersects(p.geometry, od.geometry)
WHERE p.is_project = TRUE 
  AND p.project_id IS NOT NULL
GROUP BY p.project_id;
