-- heal_project_islands.sql
-- Description: Detects project nodes isolated from the main network (LCC 1) and creates tiny "healing" links to connect them.
-- Parameters: network_table, components_table, tolerance

-- 1. Identify isolated project nodes
DROP TABLE IF EXISTS isolated_project_nodes;
CREATE TEMP TABLE isolated_project_nodes AS
SELECT DISTINCT v.id, v.the_geom
FROM {network_table}_vertices_pgr v
JOIN {network_table} n ON (v.id = n.source OR v.id = n.target)
JOIN {components_table} c ON v.id = c.node_id
WHERE n.is_project = TRUE 
  AND c.component != (SELECT component FROM {components_table} GROUP BY component ORDER BY count(*) DESC LIMIT 1);

-- 2. Find the nearest node in LCC 1 for each isolated project node
DROP TABLE IF EXISTS healing_links;
CREATE TEMP TABLE healing_links AS
SELECT DISTINCT ON (i.id)
    i.id as from_id,
    lcc1.node_id as to_id,
    ST_MakeLine(i.the_geom, lcc1.the_geom) as geom
FROM isolated_project_nodes i
CROSS JOIN LATERAL (
    SELECT c.node_id, v.the_geom
    FROM {components_table} c
    JOIN {network_table}_vertices_pgr v ON c.node_id = v.id
    WHERE c.component = (SELECT component FROM {components_table} GROUP BY component ORDER BY count(*) DESC LIMIT 1)
    ORDER BY i.the_geom <-> v.the_geom
    LIMIT 1
) lcc1
WHERE ST_Distance(i.the_geom, lcc1.the_geom) < {tolerance};

-- 3. Inject the healing links into the network
INSERT INTO {network_table} (geometry, highway, is_project, impedance)
SELECT 
    geom,
    'project_healing' as highway,
    TRUE as is_project,
    1.0 as impedance
FROM healing_links;

-- 4. Audit
DO $$
BEGIN
    RAISE NOTICE 'Healing links created: %', (SELECT count(*) FROM healing_links);
END $$;
