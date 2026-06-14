-- finalize_qgis_layers.sql
-- Phase 6: Standardizes the final output into two Master Layers for QGIS.

-- 1. Create Master Network Layer
-- We join the routing results (od_flow) with the intermodal network.
DROP TABLE IF EXISTS {scenario_prefix}_network;
CREATE TABLE {scenario_prefix}_network AS
SELECT 
    n.id as edge_id,
    n.geometry,
    n.highway,
    n.impedance,
    COALESCE(n.is_project, FALSE) as is_project,
    n.project_id,
    COALESCE(n.od_flow, 0) as od_flow,
    (COALESCE(n.od_flow, 0) / NULLIF(ST_Length(n.geometry), 0)) as cost_effective,
    TRUE as participating_in_analysis
FROM {network_table} n;

CREATE INDEX {scenario_prefix}_net_gix ON {scenario_prefix}_network USING GIST (geometry);

-- 2. Create Master H3 Layer
-- We already have the H3 table being populated in Stage 8. 
-- We just ensure it follows the naming convention and has clean columns.
DROP TABLE IF EXISTS {scenario_prefix}_h3;
CREATE TABLE {scenario_prefix}_h3 AS
SELECT 
    h3_index,
    geometry,
    COALESCE(pop_total, 0) as pop_total,
    COALESCE(od_flow, 0) as od_flow,
    COALESCE(m_osm, 0) as m_osm,
    COALESCE(m_project, 0) as m_project,
    TRUE as participating_in_analysis
FROM {h3_table};

CREATE INDEX {scenario_prefix}_h3_gix ON {scenario_prefix}_h3 USING GIST (geometry);

-- 3. Create Master Ciclo Layer
-- We provide the raw bike infrastructure as a clean layer for visualization.
DROP TABLE IF EXISTS {scenario_prefix}_ciclo;
CREATE TABLE {scenario_prefix}_ciclo AS
SELECT 
    geometry,
    'existing_bike_path' as type
FROM {ciclo_table};

-- Attempt to add impedance if it was missing from raw data
ALTER TABLE {scenario_prefix}_ciclo ADD COLUMN IF NOT EXISTS impedance FLOAT DEFAULT 0.5;

CREATE INDEX {scenario_prefix}_ciclo_gix ON {scenario_prefix}_ciclo USING GIST (geometry);

-- 4. Audit
DO $$
BEGIN
    RAISE NOTICE 'QGIS Master Layers finalized: %_network and %_h3', '{scenario_prefix}', '{scenario_prefix}';
END $$;
