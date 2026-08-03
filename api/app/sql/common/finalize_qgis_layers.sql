-- finalize_qgis_layers.sql
-- Phase 6: Standardizes the final output into two Master Layers for QGIS.

-- 1. Create Master Network Layer
DROP TABLE IF EXISTS {scenario_prefix}_network;
CREATE TABLE {scenario_prefix}_network AS
SELECT 
    n.id as edge_id,
    n.geometry,
    n.highway,
    n.original_highway,
    n.impedance,
    COALESCE(n.is_project, FALSE) as is_project,
    n.project_id,
    COALESCE(n.od_flow, 0) as od_flow,
    (COALESCE(n.od_flow, 0) / NULLIF(ST_Length(n.geometry), 0)) as cost_effective,
    TRUE as participating_in_analysis
FROM {network_table} n;

CREATE INDEX {scenario_prefix}_net_gix ON {scenario_prefix}_network USING GIST (geometry);

-- 3. Create Master Ciclo Layer
DROP TABLE IF EXISTS {scenario_prefix}_ciclo;
CREATE TABLE {scenario_prefix}_ciclo AS
SELECT 
    geometry,
    'existing_bike_path' as type
FROM {ciclo_table};

ALTER TABLE {scenario_prefix}_ciclo ADD COLUMN IF NOT EXISTS impedance FLOAT DEFAULT 0.5;

CREATE INDEX {scenario_prefix}_ciclo_gix ON {scenario_prefix}_ciclo USING GIST (geometry);

-- 4. Standardize Census blocks layer pop column to include pop_total and pop_density_m2
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
          AND table_name = '{scenario_prefix}_census'
    ) THEN
        -- Add pop_density_m2 if it does not exist
        IF NOT EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
              AND table_name = '{scenario_prefix}_census' 
              AND column_name = 'pop_density_m2'
        ) THEN
            ALTER TABLE {scenario_prefix}_census ADD COLUMN pop_density_m2 FLOAT;
        END IF;
        
        -- Remove n_per if it exists
        IF EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
              AND table_name = '{scenario_prefix}_census' 
              AND column_name = 'n_per'
        ) THEN
            ALTER TABLE {scenario_prefix}_census DROP COLUMN n_per;
        END IF;

        -- Update pop_density_m2 = pop_total / area
        UPDATE {scenario_prefix}_census 
        SET pop_density_m2 = pop_total / NULLIF(ST_Area(geometry), 0);
    END IF;
END $$;
