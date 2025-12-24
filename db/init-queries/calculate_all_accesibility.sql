CREATE OR REPLACE FUNCTION calculate_all_accessibility()
RETURNS TABLE(node_id INTEGER, accessibility DOUBLE PRECISION) AS $$
BEGIN
    RETURN QUERY
    WITH nodes AS (
        SELECT DISTINCT source AS node_id FROM my_network_table
        UNION
        SELECT DISTINCT target FROM my_network_table
    ), node_pairs AS (
        SELECT n1.node_id AS source, n2.node_id AS target
        FROM nodes n1, nodes n2
        WHERE n1.node_id <> n2.node_id
    ), distances AS (
        SELECT source, target, euclidean_distance(source, target) AS distance
        FROM node_pairs
    )
    SELECT
        source,
        SUM(1 / distance) AS accessibility
    FROM distances
    GROUP BY source
    ORDER BY source;
END;
$$ LANGUAGE plpgsql;
