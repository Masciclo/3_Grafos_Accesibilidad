-- link_single_edge_project.sql
-- Description: System for linking single-edge projects by defining a project zone, 
-- planarizing with nearby reference edges, and snapping dangling vertices.
-- Parameters: network_table, pid, mr_distance (snap), zp_distance (zone)

-- 1. DEFINE PROJECT ZONE & GET NEARBY REFERENCE EDGES
DROP TABLE IF EXISTS project_zone_context;
CREATE TEMP TABLE project_zone_context AS
SELECT id, geometry, highway, is_project, project_id, parent_baseline_id, impedance
FROM {network_table}
WHERE (project_id = '{pid}' AND is_project = TRUE)
   OR (is_project = FALSE AND id IN (
       SELECT base.id FROM {network_table} base, {network_table} proj
       WHERE proj.project_id = '{pid}' AND proj.is_project = TRUE
         AND ST_DWithin(base.geometry, proj.geometry, {zp_distance})
         AND base.is_project = FALSE
   ));

-- 2. PLANARIZE TO CHECK FOR ANY INTERSECTION
-- We use ST_Node(ST_Union) on the context
DO $$
BEGIN
    IF (SELECT count(*) FROM project_zone_context WHERE is_project = TRUE) > 0 THEN
        -- Delete original segments from main table
        DELETE FROM {network_table} WHERE id IN (SELECT id FROM project_zone_context);

        -- Insert nodalized fragments
        INSERT INTO {network_table} (geometry, highway, is_project, project_id, parent_baseline_id, impedance)
        WITH nodalized AS (
            SELECT (ST_Dump(ST_Node(ST_SnapToGrid(ST_Union(geometry), 0.001)))).geom as g
            FROM project_zone_context
        )
        SELECT 
            n.g,
            ctx.highway,
            ctx.is_project,
            ctx.project_id,
            ctx.parent_baseline_id,
            ctx.impedance
        FROM nodalized n
        JOIN project_zone_context ctx ON ST_Intersects(n.g, ST_Buffer(ctx.geometry, 0.001))
        WHERE ST_Dimension(n.g) = 1
        GROUP BY n.g, ctx.highway, ctx.is_project, ctx.project_id, ctx.parent_baseline_id, ctx.impedance;
    END IF;
END $$;

-- 3. SNAP DISCONNECTED VERTICES TO CLOSEST REFERENCE VERTEX
-- Identify vertices of the project that are NOT connected to any reference edge
DO $$
DECLARE
    dangling_record RECORD;
    target_node_geom GEOMETRY;
BEGIN
    FOR dangling_record IN (
        WITH project_vertices AS (
            SELECT ST_StartPoint(geometry) as v, id FROM {network_table} WHERE project_id = '{pid}' AND is_project = TRUE
            UNION
            SELECT ST_EndPoint(geometry) as v, id FROM {network_table} WHERE project_id = '{pid}' AND is_project = TRUE
        ),
        dangling_vertices AS (
            -- A vertex is dangling if it doesn't intersect any reference geometry (is_project=FALSE)
            -- or any other vertex from a different edge
            SELECT pv.v, pv.id as edge_id
            FROM project_vertices pv
            WHERE NOT EXISTS (
                SELECT 1 FROM {network_table} ref 
                WHERE ref.is_project = FALSE 
                  AND ST_Intersects(pv.v, ref.geometry)
            )
        )
        SELECT * FROM dangling_vertices
    ) LOOP
        -- Find closest reference vertex within mr_distance
        SELECT ST_ClosestPoint(ST_Collect(ST_StartPoint(geometry), ST_EndPoint(geometry)), dangling_record.v) INTO target_node_geom
        FROM {network_table}
        WHERE is_project = FALSE AND ST_DWithin(geometry, dangling_record.v, {mr_distance});

        IF target_node_geom IS NOT NULL THEN
            -- Update project edge geometry to snap to target
            UPDATE {network_table} 
            SET geometry = CASE 
                WHEN ST_Equals(ST_StartPoint(geometry), dangling_record.v) THEN ST_SetPoint(geometry, 0, target_node_geom)
                WHEN ST_Equals(ST_EndPoint(geometry), dangling_record.v) THEN ST_SetPoint(geometry, ST_NPoints(geometry)-1, target_node_geom)
                ELSE geometry
            END
            WHERE id = dangling_record.edge_id;
        END IF;
    END LOOP;
END $$;

-- 4. FINAL CLEANUP FOR THIS PID
UPDATE {network_table} SET 
    length = ST_Length(geometry),
    cost = ST_Length(geometry) * COALESCE(impedance, 1.0)
WHERE project_id = '{pid}';
