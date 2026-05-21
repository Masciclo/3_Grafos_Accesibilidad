-- snap_and_shatter_projects.sql
-- Description: Snaps project endpoints to the nearest OSM line within a tolerance and shatters the OSM network to create connectivity nodes.
-- Parameters: network_table, projects_table, tolerance

-- 1. Create a temporary table of project endpoints
DROP TABLE IF EXISTS project_endpoints;
CREATE TEMP TABLE project_endpoints AS
SELECT 
    id as proj_id,
    ST_StartPoint(geometry) as geom
FROM {projects_table}
UNION ALL
SELECT 
    id as proj_id,
    ST_EndPoint(geometry) as geom
FROM {projects_table};

-- 2. Find nearest OSM lines for these endpoints within tolerance (e.g., 5 meters)
DROP TABLE IF EXISTS snapping_points;
CREATE TEMP TABLE snapping_points AS
SELECT DISTINCT ON (e.proj_id, e.geom)
    e.proj_id,
    e.geom as orig_geom,
    n.id as osm_id,
    ST_ClosestPoint(n.geometry, e.geom) as snapped_geom
FROM project_endpoints e
CROSS JOIN LATERAL (
    SELECT id, geometry 
    FROM {network_table} 
    WHERE ST_DWithin(e.geom, geometry, {tolerance})
    ORDER BY ST_Distance(e.geom, geometry)
    LIMIT 1
) n;

-- 3. Shatter the OSM lines at the snapped points
-- This is a complex operation: we replace the original OSM line with two fragments
-- only if a snap occurred.
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN SELECT * FROM snapping_points LOOP
        -- Only split if the snapped point is not already a vertex (start/end)
        IF NOT ST_Equals(r.snapped_geom, ST_StartPoint((SELECT geometry FROM {network_table} WHERE id = r.osm_id)))
           AND NOT ST_Equals(r.snapped_geom, ST_EndPoint((SELECT geometry FROM {network_table} WHERE id = r.osm_id))) THEN
           
           -- Create new fragments and delete original
           INSERT INTO {network_table} (geometry, highway, is_project, impedance)
           SELECT 
                (ST_Dump(ST_Split(ST_Snap(n.geometry, r.snapped_geom, 0.1), r.snapped_geom))).geom,
                n.highway,
                n.is_project,
                n.impedance
           FROM {network_table} n
           WHERE n.id = r.osm_id;
           
           DELETE FROM {network_table} WHERE id = r.osm_id;
        END IF;
        
        -- Update the project geometry to perfectly touch the snapped point
        UPDATE {projects_table} p
        SET geometry = ST_SetPoint(
            p.geometry, 
            CASE WHEN ST_Equals(ST_StartPoint(p.geometry), r.orig_geom) THEN 0 ELSE ST_NPoints(p.geometry)-1 END,
            r.snapped_geom
        )
        WHERE p.id = r.proj_id;
    END LOOP;
END $$;
