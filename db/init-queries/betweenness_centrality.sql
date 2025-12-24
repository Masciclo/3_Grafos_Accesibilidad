CREATE OR REPLACE FUNCTION betweenness_centrality(
    network_table text,
    source_column text,
    target_column text,
    edge_weight_column text,
    directed boolean DEFAULT true
)
RETURNS TABLE (id integer, betweenness double precision) AS $$
DECLARE
    node_count integer;
BEGIN
    EXECUTE format('SELECT COUNT(DISTINCT %I) FROM %I', source_column, network_table) INTO node_count;

    RETURN QUERY EXECUTE format('
        WITH edges AS (
            SELECT %I AS source, %I AS target, %I AS cost, 1 AS path_count
            FROM %I
        ),
        node_paths AS (
            SELECT DISTINCT ON (node, path_id) node, cost, path_id
            FROM (
                SELECT start_vid AS node, edge_cost AS cost, path_id, rank() OVER (PARTITION BY path_id ORDER BY edge_seq) AS edge_rank
                FROM pgr_dijkstra(
                    ''SELECT id, source, target, %I AS cost, %L AS directed FROM %I'',
                    ARRAY(SELECT DISTINCT %I FROM %I),
                    ARRAY(SELECT DISTINCT %I FROM %I),
                    %L
                ) AS dijkstra
            ) AS paths
            WHERE edge_rank = 1
        ),
        edge_paths AS (
            SELECT source, target, count(*) AS path_count
            FROM (
                SELECT node, path_id
                FROM node_paths
                GROUP BY node, path_id
            ) AS paths
            JOIN %I AS network ON paths.node = network.%I
            GROUP BY source, target
        ),
        edge_betweenness AS (
            SELECT source, target, sum(path_count * edge_paths.path_count * 1.0 / node_count) AS betweenness
            FROM edge_paths
            JOIN edges ON edges.source = edge_paths.source AND edges.target = edge_paths.target
            CROSS JOIN (SELECT node_count) AS stats
            GROUP BY source, target
        ),
        node_betweenness AS (
            SELECT DISTINCT ON (node) node, sum(betweenness) OVER (PARTITION BY node) AS betweenness
            FROM (
                SELECT source AS node, betweenness FROM edge_betweenness
                UNION ALL
                SELECT target AS node, betweenness FROM edge_betweenness
            ) AS node_betweenness
        )
        SELECT %I, betweenness
        FROM node_betweenness
        ORDER BY %I;
    ', source_column, edge_weight_column, network_table, edge_weight_column, directed, network_table, source_column, network_table, source_column, network_table, target_column, network_table, network_table, source_column);

END;
$$ LANGUAGE plpgsql;
