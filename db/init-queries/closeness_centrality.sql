CREATE OR REPLACE FUNCTION closeness_centrality(
    network_table text,
    source_column text,
    target_column text,
    edge_weight_column text,
    directed boolean DEFAULT true
)
RETURNS TABLE (id integer, closeness double precision) AS $$
DECLARE
    node_count integer;
BEGIN
    EXECUTE format('SELECT COUNT(DISTINCT %I) FROM %I', source_column, network_table) INTO node_count;

    RETURN QUERY EXECUTE format('
        WITH paths AS (
            SELECT DISTINCT ON (target) target, array_agg(length ORDER BY length ASC) AS lengths
            FROM (SELECT %I AS target, %I AS source, %I AS length FROM %I
                  UNION ALL
                  SELECT %I AS target, %I AS source, %I AS length FROM %I WHERE %s)
                AS edges
            JOIN (SELECT DISTINCT %I AS node FROM %I) AS nodes
            ON edges.target = nodes.node
            WHERE NOT %s(edges.%I, 0)
            GROUP BY target
        )
        SELECT id, CASE WHEN sum(lengths) = 0 THEN 0 ELSE (%s - 1) * 1.0 / sum(lengths) END AS closeness
        FROM (SELECT * FROM %I WHERE %s) AS nodes
        LEFT JOIN paths ON nodes.%I = paths.target
        ORDER BY id;
    ', target_column, source_column, edge_weight_column, network_table, source_column, target_column, edge_weight_column, network_table, CASE WHEN directed THEN '' ELSE 'coalesce' END, target_column, network_table, CASE WHEN directed THEN '' ELSE 'coalesce' END, edge_weight_column, node_count, network_table, CASE WHEN directed THEN '' ELSE 'coalesce' END, target_column);
END;
$$ LANGUAGE plpgsql;
