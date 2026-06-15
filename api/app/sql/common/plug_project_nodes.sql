-- plug_project_nodes.sql
-- Task 19.5 (Fixed Logic): Forcibly plugs disconnected project nodes into the nearest city node.
-- Parameters: network_table, mr_distance (Magnetismo a Referencia), pid

-- 1. IDENTIFY ALL NODES OF THE CURRENT PROJECT
DROP TABLE IF EXISTS current_project_nodes;
CREATE TEMP TABLE current_project_nodes AS
SELECT DISTINCT node_id FROM (
    SELECT source as node_id FROM {network_table} WHERE project_id = '{pid}'
    UNION
    SELECT target FROM {network_table} WHERE project_id = '{pid}'
) sub;

-- 2. IDENTIFY ISOLATED PROJECT NODES
-- These are nodes that are only connected to the current project segments.
DROP TABLE IF EXISTS isolated_project_nodes;
CREATE TEMP TABLE isolated_project_nodes AS
SELECT 
    cpn.node_id,
    v.the_geom
FROM current_project_nodes cpn
JOIN {network_table}_vertices_pgr v ON cpn.node_id = v.id
WHERE NOT EXISTS (
    SELECT 1 FROM {network_table} e 
    WHERE (e.source = cpn.node_id OR e.target = cpn.node_id) 
      AND (e.project_id != '{pid}' OR e.project_id IS NULL)
);

-- 3. FIND NEAREST TARGET NODES FROM THE REST OF THE CITY
-- Target node MUST be a node already connected to the non-project network.
DROP TABLE IF EXISTS plugging_map;
CREATE TEMP TABLE plugging_map AS
SELECT DISTINCT ON (i.node_id)
    i.node_id as isolated_node_id,
    target.id as target_node_id
FROM isolated_project_nodes i
CROSS JOIN LATERAL (
    SELECT v.id 
    FROM {network_table}_vertices_pgr v
    WHERE v.id NOT IN (SELECT node_id FROM isolated_project_nodes) -- Don't snap to other isolated project nodes
      AND ST_DWithin(i.the_geom, v.the_geom, {mr_distance})
      -- MUST be connected to the city
      AND EXISTS (SELECT 1 FROM {network_table} e WHERE (e.source = v.id OR e.target = v.id) AND (e.project_id != '{pid}' OR e.project_id IS NULL))
    ORDER BY i.the_geom <-> v.the_geom
    LIMIT 1
) target;

-- 4. FORCE UPDATE TOPOLOGY
UPDATE {network_table} SET source = m.target_node_id FROM plugging_map m WHERE source = m.isolated_node_id AND project_id = '{pid}';
UPDATE {network_table} SET target = m.target_node_id FROM plugging_map m WHERE target = m.isolated_node_id AND project_id = '{pid}';

-- 5. Audit
DO $$
BEGIN
    RAISE NOTICE 'Forced plugging complete for Project %. Nodes plugged: %', 
        '{pid}', (SELECT COUNT(*) FROM plugging_map);
END $$;
