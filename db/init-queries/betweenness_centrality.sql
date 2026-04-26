CREATE OR REPLACE FUNCTION betweenness_centrality(
    network_table text,
    edge_weight_column text DEFAULT 'cost',
    directed boolean DEFAULT false
)
RETURNS TABLE (edge_id bigint, betweenness numeric) AS $$
DECLARE
    node_count integer;
BEGIN
    -- 1. Contar nodos únicos para la normalización
    EXECUTE format('SELECT COUNT(DISTINCT source) FROM %I', network_table) INTO node_count;

    -- 2. Ejecutar ruteo Many-to-Many y acumular uso de arcos
    RETURN QUERY EXECUTE format('
        WITH paths AS (
            SELECT edge::bigint, 1.0 as flow
            FROM pgr_dijkstra(
                ''SELECT id, source, target, %I AS cost FROM %I'',
                ARRAY(SELECT id FROM %I_vertices_pgr),
                ARRAY(SELECT id FROM %I_vertices_pgr),
                %L
            )
            WHERE edge != -1
        )
        SELECT edge as edge_id, SUM(flow) / %L as betweenness
        FROM paths
        GROUP BY edge
        ORDER BY edge_id;
    ', edge_weight_column, network_table, network_table, network_table, directed, node_count);

END;
$$ LANGUAGE plpgsql;
