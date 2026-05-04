-- 1. Create a temporary table to store the results of the ruteo
-- We use a permanent table (prefixed with city name) to allow Python to insert into it across sessions
DROP TABLE IF EXISTS {network_table}_betweenness_results;
CREATE TABLE {network_table}_betweenness_results (
    edge_id bigint,
    flow numeric
);

-- Create index to speed up the final aggregation
CREATE INDEX IF NOT EXISTS {network_table}_btwn_idx ON {network_table}_betweenness_results (edge_id);
