-- snap_h3_to_network.sql
-- Description: Snapping of H3 hexagons to the network (pgRouting vertices)
-- Logic: Snaps only to nodes within the Largest Connected Component (LCC)
-- Phase 3 Refinement: Includes a distance threshold (250m) to identify Coverage Loss.

DO $$
DECLARE
    target_component_id integer;
    lcc_exists boolean;
    snap_threshold_val float := 250.0; -- Default threshold in meters
    total_cells integer;
    loss_count integer;
    loss_pct numeric;
BEGIN
    -- 1. Check if the components table exists
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_name = '{components_table}'
    ) INTO lcc_exists;

    -- 2. Identify the Giant Component (LCC) ID
    IF lcc_exists THEN
        SELECT component INTO target_component_id
        FROM {components_table}_nodes
        GROUP BY component
        ORDER BY count(*) DESC
        LIMIT 1;
        RAISE NOTICE 'LCC detectado (ID: %). Snapping restringido a red conectada.', target_component_id;
    ELSE
        RAISE WARNING 'Components table not found. Snapping to ANY node (Risk of disconnected routing).';
    END IF;

    -- 3. Create Mapping Table: H3 -> Node
    DROP TABLE IF EXISTS {location_prefix}_h3_to_node;
    CREATE TABLE {location_prefix}_h3_to_node AS
    WITH h3_centroids AS (
        SELECT 
            h3_index, 
            ST_Centroid(geometry) as geom
        FROM {h3_table}
    )
    SELECT 
        h.h3_index,
        n.id as node_id,
        n.dist as snap_distance,
        CASE 
            WHEN n.dist > snap_threshold_val THEN true 
            ELSE false 
        END as is_coverage_loss,
        CASE WHEN lcc_exists THEN target_component_id ELSE NULL END as lcc_id
    FROM h3_centroids h
    CROSS JOIN LATERAL (
        SELECT id, the_geom, ST_Distance(h.geom, the_geom) as dist
        FROM {network_table}_vertices_pgr v
        WHERE 
            -- If LCC exists, filter by it
            (NOT lcc_exists OR EXISTS (
                SELECT 1 FROM {components_table}_nodes c 
                WHERE c.id = v.id AND c.component = target_component_id
            ))
        ORDER BY h.geom <-> v.the_geom
        LIMIT 1
    ) n;

    -- 4. Audit Log
    SELECT COUNT(*) INTO total_cells FROM {h3_table};
    SELECT COUNT(*) INTO loss_count FROM {location_prefix}_h3_to_node WHERE is_coverage_loss = true;
    
    IF total_cells > 0 THEN
        loss_pct := ROUND((loss_count::float / total_cells * 100)::numeric, 2);
    ELSE
        loss_pct := 0;
    END IF;

    RAISE NOTICE 'Snapping completado.';
    RAISE NOTICE 'Threshold used: %m', snap_threshold_val;
    RAISE NOTICE 'Coverage Loss: % cells (% de la red) de la tabla %_nodes', loss_count, loss_pct, '{components_table}';

END $$;
