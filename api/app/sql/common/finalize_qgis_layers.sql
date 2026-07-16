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

-- 2. Create Master H3 Layer with Dynamic OD Origin/Destination check
DROP TABLE IF EXISTS {scenario_prefix}_h3;

DO $$
DECLARE
    od_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
          AND table_name = '{scenario_prefix}_od_matrix'
    ) INTO od_exists;

    IF od_exists THEN
        EXECUTE '
            CREATE TABLE {scenario_prefix}_h3 AS
            WITH home_trips AS (
                SELECT h3_dest, SUM(trips_returning_home) as trips_home
                FROM {scenario_prefix}_od_matrix
                GROUP BY h3_dest
            ),
            dest_trips AS (
                SELECT h3_dest, SUM(trips_outgoing_destinations) as trips_dest
                FROM {scenario_prefix}_od_matrix
                GROUP BY h3_dest
            )
            SELECT 
                h3.h3_index,
                h3.geometry,
                COALESCE(h3.pop_total, 0) as pop_total,
                COALESCE(h3.od_flow, 0) as od_flow,
                COALESCE(h3.m_osm, 0) as m_osm,
                COALESCE(h3.m_project, 0) as m_project,
                COALESCE(h.trips_home, 0)::FLOAT as trips_returning_home,
                COALESCE(d.trips_dest, 0)::FLOAT as trips_outgoing_destinations,
                TRUE as participating_in_analysis
            FROM {h3_table} h3
            LEFT JOIN home_trips h ON h3.h3_index::text = h.h3_dest::text
            LEFT JOIN dest_trips d ON h3.h3_index::text = d.h3_dest::text;
        ';
    ELSE
        EXECUTE '
            CREATE TABLE {scenario_prefix}_h3 AS
            SELECT 
                h3_index,
                geometry,
                COALESCE(pop_total, 0) as pop_total,
                COALESCE(od_flow, 0) as od_flow,
                COALESCE(m_osm, 0) as m_osm,
                COALESCE(m_project, 0) as m_project,
                0.0::FLOAT as trips_returning_home,
                0.0::FLOAT as trips_outgoing_destinations,
                TRUE as participating_in_analysis
            FROM {h3_table};
        ';
    END IF;
END $$;

CREATE INDEX {scenario_prefix}_h3_gix ON {scenario_prefix}_h3 USING GIST (geometry);

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

-- 5. Audit
DO $$
BEGIN
    RAISE NOTICE 'QGIS Master Layers finalized: %_network, %_h3 and %_census', '{scenario_prefix}', '{scenario_prefix}', '{scenario_prefix}';
END $$;
