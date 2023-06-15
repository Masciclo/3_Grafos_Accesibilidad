CREATE TABLE my_network_table (
    id SERIAL PRIMARY KEY,
    source integer,
    target integer,
    length double precision
);

INSERT INTO my_network_table (source, target, length) VALUES
(1, 2, 10),
(1, 3, 5),
(2, 3, 2),
(2, 4, 3),
(3, 2, 3),
(3, 4, 1),
(3, 5, 2),
(4, 5, 4),
(5, 4, 6);

CREATE TABLE node_coordinates (
    node_id INTEGER PRIMARY KEY,
    x DOUBLE PRECISION,
    y DOUBLE PRECISION
);

INSERT INTO node_coordinates (node_id, x, y) VALUES
(1, 0, 0),
(2, 10, 0),
(3, 0, 5),
(4, 10, 10),
(5, 0, 15);


WITH nodes AS (
    SELECT DISTINCT source AS node_id FROM my_network_table
    UNION
    SELECT DISTINCT target FROM my_network_table
), node_pairs AS (
    SELECT n1.node_id AS source, n2.node_id AS target
    FROM nodes n1, nodes n2
    WHERE n1.node_id < n2.node_id
), shortest_paths AS (
    SELECT source, target, sum_shortest_path_lengths(source, target) AS path_length
    FROM node_pairs
)
SELECT
    node_id,
    SUM(path_length) AS betweenness_centrality
FROM (
    SELECT source AS node_id, path_length FROM shortest_paths
    UNION ALL
    SELECT target AS node_id, path_length FROM shortest_paths
) AS all_paths
GROUP BY node_id
ORDER BY node_id;


WITH nodes AS (
    SELECT DISTINCT source AS node_id FROM my_network_table
    UNION
    SELECT DISTINCT target FROM my_network_table
), node_pairs AS (
    SELECT n1.node_id AS source, n2.node_id AS target
    FROM nodes n1, nodes n2
    WHERE n1.node_id <> n2.node_id
)
SELECT
    source,
    target,
    euclidean_distance(source, target) AS euclidean_distance,
    shortest_path_distance(source, target) AS shortest_path_distance,
    euclidean_distance(source, target) / shortest_path_distance(source, target) AS straightness_index
FROM node_pairs
ORDER BY source, target;