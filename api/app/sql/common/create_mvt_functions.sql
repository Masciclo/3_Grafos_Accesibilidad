-- ====================================================================
-- +Ciclo Vector Tile Infrastructure: Server-Side PostGIS MVT Functions
-- Dynamic Zoom-Level Level-of-Detail (LoD) and Topology Simplification
-- Martin-compatible Function Sources with query_params json argument
-- ====================================================================

-- 1. Network & Bicycle Flow Vector Tile Function
CREATE OR REPLACE FUNCTION public.mvt_network(
    z integer, x integer, y integer, query_params json DEFAULT NULL
) RETURNS bytea AS $$
DECLARE
    envelope geometry := ST_TileEnvelope(z, x, y);
    scenario text := COALESCE(query_params->>'scenario', 'valdivia_baseline');
    tbl_name text := scenario || '_network';
    srid_val integer;
    tol float;
    result bytea;
    table_exists boolean;
    has_orig_hw boolean;
    has_proj_id boolean;
    has_impedance boolean;
    orig_hw_col text;
    proj_id_col text;
    impedance_col text;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = tbl_name
    ) INTO table_exists;

    IF NOT table_exists THEN
        RETURN ''::bytea;
    END IF;

    SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=tbl_name AND column_name='original_highway') INTO has_orig_hw;
    SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=tbl_name AND column_name='project_id') INTO has_proj_id;
    SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=tbl_name AND column_name='impedance') INTO has_impedance;

    orig_hw_col := CASE WHEN has_orig_hw THEN 'COALESCE(t.original_highway, t.highway)' ELSE 't.highway' END;
    proj_id_col := CASE WHEN has_proj_id THEN 'COALESCE(t.project_id, '''')' ELSE '''''' END;
    impedance_col := CASE WHEN has_impedance THEN 'COALESCE(t.impedance, 0)' ELSE '0' END;

    BEGIN
        EXECUTE format('SELECT COALESCE(NULLIF(ST_SRID(geometry), 0), 32719) FROM %I LIMIT 1', tbl_name) INTO srid_val;
    EXCEPTION WHEN OTHERS THEN
        srid_val := 32719;
    END;
    IF srid_val IS NULL OR srid_val = 0 THEN
        srid_val := 32719;
    END IF;

    tol := CASE 
        WHEN z < 10 THEN 25.0
        WHEN z < 12 THEN 8.0
        WHEN z < 14 THEN 2.0
        ELSE 0.0
    END;

    EXECUTE format('
        WITH bounds AS (
            SELECT ST_Transform($1, $4) AS geom_native
        ),
        edges AS (
            SELECT 
                t.edge_id,
                t.highway,
                %s AS original_highway,
                COALESCE(t.od_flow, 0)::float8 AS od_flow,
                COALESCE(t.is_project, FALSE) AS is_project,
                %s AS project_id,
                (%s)::float8 AS impedance,
                CASE 
                    WHEN $3 > 0 THEN ST_Simplify(t.geometry, $3)
                    ELSE t.geometry 
                END AS geom
            FROM %I t, bounds b
            WHERE t.geometry && b.geom_native
              AND (
                  ($2 < 13 AND (t.highway IN (''motorway'', ''trunk'', ''primary'', ''secondary'', ''tertiary'', ''cycleway'') OR t.is_project = TRUE OR t.od_flow > 0))
                  OR ($2 >= 13)
              )
        )
        SELECT ST_AsMVT(tile, ''network'', 4096, ''geom'')
        FROM (
            SELECT 
                edge_id, highway, original_highway, od_flow, is_project, project_id, impedance,
                ST_AsMVTGeom(ST_Transform(geom, 3857), $1, 4096, 64, true) AS geom
            FROM edges
            WHERE geom IS NOT NULL
        ) tile;', orig_hw_col, proj_id_col, impedance_col, tbl_name)
    INTO result
    USING envelope, z, tol, srid_val;

    RETURN result;
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE;

-- 2. Delta Flow Differential Vector Tile Function
CREATE OR REPLACE FUNCTION public.mvt_delta(
    z integer, x integer, y integer, query_params json DEFAULT NULL
) RETURNS bytea AS $$
DECLARE
    envelope geometry := ST_TileEnvelope(z, x, y);
    scenario text := COALESCE(query_params->>'scenario', 'valdivia_project');
    tbl_name text := scenario || '_delta_network';
    srid_val integer;
    tol float;
    result bytea;
    table_exists boolean;
    has_proj_id boolean;
    proj_id_col text;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = tbl_name
    ) INTO table_exists;

    IF NOT table_exists THEN
        RETURN ''::bytea;
    END IF;

    SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=tbl_name AND column_name='project_id') INTO has_proj_id;
    proj_id_col := CASE WHEN has_proj_id THEN 'COALESCE(d.project_id, '''')' ELSE '''''' END;

    BEGIN
        EXECUTE format('SELECT COALESCE(NULLIF(ST_SRID(geometry), 0), 32719) FROM %I LIMIT 1', tbl_name) INTO srid_val;
    EXCEPTION WHEN OTHERS THEN
        srid_val := 32719;
    END;
    IF srid_val IS NULL OR srid_val = 0 THEN
        srid_val := 32719;
    END IF;

    tol := CASE 
        WHEN z < 10 THEN 25.0
        WHEN z < 12 THEN 8.0
        WHEN z < 14 THEN 2.0
        ELSE 0.0
    END;

    EXECUTE format('
        WITH bounds AS (
            SELECT ST_Transform($1, $4) AS geom_native
        ),
        edges AS (
            SELECT 
                d.edge_id,
                COALESCE(d.delta_flow, 0)::float8 AS delta_flow,
                COALESCE(d.flow_current, 0)::float8 AS flow_current,
                COALESCE(d.flow_baseline, 0)::float8 AS flow_baseline,
                COALESCE(d.is_project, FALSE) AS is_project,
                %s AS project_id,
                CASE 
                    WHEN $3 > 0 THEN ST_Simplify(d.geometry, $3)
                    ELSE d.geometry 
                END AS geom
            FROM %I d, bounds b
            WHERE d.geometry && b.geom_native
              AND (
                  ($2 < 13 AND (ABS(d.delta_flow) > 0 OR d.is_project = TRUE))
                  OR ($2 >= 13)
              )
        )
        SELECT ST_AsMVT(tile, ''delta'', 4096, ''geom'')
        FROM (
            SELECT 
                edge_id, delta_flow, flow_current, flow_baseline, is_project, project_id,
                ST_AsMVTGeom(ST_Transform(geom, 3857), $1, 4096, 64, true) AS geom
            FROM edges
            WHERE geom IS NOT NULL
        ) tile;', proj_id_col, tbl_name)
    INTO result
    USING envelope, z, tol, srid_val;

    RETURN result;
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE;

-- 3. Urban Context (Water, Green Areas, Urban Limit) Vector Tile Function
CREATE OR REPLACE FUNCTION public.mvt_context(
    z integer, x integer, y integer, query_params json DEFAULT NULL
) RETURNS bytea AS $$
DECLARE
    envelope geometry := ST_TileEnvelope(z, x, y);
    city_key text := COALESCE(query_params->>'city_key', 'valdivia');
    water_tbl text;
    forest_tbl text;
    green_tbl text;
    f_src text;
    limit_tbl text;
    build_tbl text;
    water_tile bytea := ''::bytea;
    forest_tile bytea := ''::bytea;
    build_tile bytea := ''::bytea;
    limit_tile bytea := ''::bytea;
    srid_val integer;
BEGIN
    -- 1. Resolve Water Table
    SELECT table_name INTO water_tbl FROM information_schema.tables 
    WHERE table_schema = 'public' 
      AND (table_name = city_key || '_water' OR table_name = left(city_key, 4) || 'chil_water' OR table_name LIKE '%' || left(city_key, 4) || '%water%')
    ORDER BY length(table_name) ASC LIMIT 1;

    -- 2. Resolve Forest Table
    SELECT table_name INTO forest_tbl FROM information_schema.tables 
    WHERE table_schema = 'public' 
      AND (table_name = city_key || '_forests' OR table_name = left(city_key, 4) || 'chil_forests' OR table_name LIKE '%' || left(city_key, 4) || '%forest%')
    ORDER BY length(table_name) ASC LIMIT 1;

    -- 3. Resolve Green Areas Table
    SELECT table_name INTO green_tbl FROM information_schema.tables 
    WHERE table_schema = 'public' 
      AND (table_name = city_key || '_green_areas' OR table_name = left(city_key, 4) || 'chil_green_areas' OR table_name LIKE '%' || left(city_key, 4) || '%green%')
    ORDER BY length(table_name) ASC LIMIT 1;

    -- 4. Resolve Urban Limit Table
    SELECT table_name INTO limit_tbl FROM information_schema.tables 
    WHERE table_schema = 'public' 
      AND (table_name = city_key || '_urban_limit' OR table_name = left(city_key, 4) || 'chil_urban_limit' OR table_name LIKE '%' || left(city_key, 4) || '%limit%')
    ORDER BY length(table_name) ASC LIMIT 1;

    -- 5. Resolve Buildings Table
    SELECT table_name INTO build_tbl FROM information_schema.tables 
    WHERE table_schema = 'public' 
      AND (table_name = city_key || '_buildings' OR table_name = left(city_key, 4) || 'chil_buildings' OR table_name LIKE '%' || left(city_key, 4) || '%building%')
    ORDER BY length(table_name) ASC LIMIT 1;

    IF water_tbl IS NULL AND forest_tbl IS NULL AND green_tbl IS NULL AND limit_tbl IS NULL AND build_tbl IS NULL THEN
        RETURN ''::bytea;
    END IF;

    -- Stream Water (simplified at low zoom)
    IF water_tbl IS NOT NULL THEN
        BEGIN
            EXECUTE format('SELECT COALESCE(NULLIF(ST_SRID(geometry), 0), 32719) FROM %I LIMIT 1', water_tbl) INTO srid_val;
        EXCEPTION WHEN OTHERS THEN srid_val := 32719; END;
        IF srid_val IS NULL OR srid_val = 0 THEN srid_val := 32719; END IF;
        EXECUTE format('
            WITH bounds AS (SELECT ST_Transform($1, $2) AS geom_native)
            SELECT ST_AsMVT(t, ''water'', 4096, ''geom'')
            FROM (
                SELECT ST_AsMVTGeom(ST_Transform(CASE WHEN $3 < 11 THEN ST_Simplify(w.geometry, 10.0) ELSE w.geometry END, 3857), $1, 4096, 64, true) AS geom
                FROM %I w, bounds b
                WHERE w.geometry && b.geom_native
            ) t WHERE geom IS NOT NULL;', water_tbl)
        INTO water_tile USING envelope, srid_val, z;
    END IF;

    -- Stream Forests / Greenery (combine forest_tbl and green_tbl into ''forests'' layer)
    IF forest_tbl IS NOT NULL OR green_tbl IS NOT NULL THEN
        IF forest_tbl IS NOT NULL AND green_tbl IS NOT NULL THEN
            f_src := format('(SELECT geometry FROM %I UNION ALL SELECT geometry FROM %I)', forest_tbl, green_tbl);
            BEGIN
                EXECUTE format('SELECT COALESCE(NULLIF(ST_SRID(geometry), 0), 32719) FROM %I LIMIT 1', forest_tbl) INTO srid_val;
            EXCEPTION WHEN OTHERS THEN srid_val := 32719; END;
        ELSIF forest_tbl IS NOT NULL THEN
            f_src := forest_tbl;
            BEGIN
                EXECUTE format('SELECT COALESCE(NULLIF(ST_SRID(geometry), 0), 32719) FROM %I LIMIT 1', forest_tbl) INTO srid_val;
            EXCEPTION WHEN OTHERS THEN srid_val := 32719; END;
        ELSE
            f_src := green_tbl;
            BEGIN
                EXECUTE format('SELECT COALESCE(NULLIF(ST_SRID(geometry), 0), 32719) FROM %I LIMIT 1', green_tbl) INTO srid_val;
            EXCEPTION WHEN OTHERS THEN srid_val := 32719; END;
        END IF;
        IF srid_val IS NULL OR srid_val = 0 THEN srid_val := 32719; END IF;

        EXECUTE format('
            WITH bounds AS (SELECT ST_Transform($1, $2) AS geom_native)
            SELECT ST_AsMVT(t, ''forests'', 4096, ''geom'')
            FROM (
                SELECT ST_AsMVTGeom(ST_Transform(CASE WHEN $3 < 11 THEN ST_Simplify(f.geometry, 10.0) ELSE f.geometry END, 3857), $1, 4096, 64, true) AS geom
                FROM %s f, bounds b
                WHERE f.geometry && b.geom_native
            ) t WHERE geom IS NOT NULL;', f_src)
        INTO forest_tile USING envelope, srid_val, z;
    END IF;

    -- Stream Buildings (from zoom >= 10 with progressive simplification)
    IF build_tbl IS NOT NULL AND z >= 10 THEN
        BEGIN
            EXECUTE format('SELECT COALESCE(NULLIF(ST_SRID(geometry), 0), 32719) FROM %I LIMIT 1', build_tbl) INTO srid_val;
        EXCEPTION WHEN OTHERS THEN srid_val := 32719; END;
        IF srid_val IS NULL OR srid_val = 0 THEN srid_val := 32719; END IF;
        EXECUTE format('
            WITH bounds AS (SELECT ST_Transform($1, $2) AS geom_native)
            SELECT ST_AsMVT(t, ''buildings'', 4096, ''geom'')
            FROM (
                SELECT ST_AsMVTGeom(ST_Transform(CASE WHEN $3 < 12 THEN ST_Simplify(b.geometry, 5.0) ELSE b.geometry END, 3857), $1, 4096, 64, true) AS geom
                FROM %I b, bounds bnd
                WHERE b.geometry && bnd.geom_native
            ) t WHERE geom IS NOT NULL;', build_tbl)
        INTO build_tile USING envelope, srid_val, z;
    END IF;

    -- Stream Urban Limit
    IF limit_tbl IS NOT NULL THEN
        BEGIN
            EXECUTE format('SELECT COALESCE(NULLIF(ST_SRID(geometry), 0), 32719) FROM %I LIMIT 1', limit_tbl) INTO srid_val;
        EXCEPTION WHEN OTHERS THEN srid_val := 32719; END;
        IF srid_val IS NULL OR srid_val = 0 THEN srid_val := 32719; END IF;
        EXECUTE format('
            WITH bounds AS (SELECT ST_Transform($1, $2) AS geom_native)
            SELECT ST_AsMVT(t, ''urban_limit'', 4096, ''geom'')
            FROM (
                SELECT ST_AsMVTGeom(ST_Transform(l.geometry, 3857), $1, 4096, 64, true) AS geom
                FROM %I l, bounds b
                WHERE l.geometry && b.geom_native
            ) t WHERE geom IS NOT NULL;', limit_tbl)
        INTO limit_tile USING envelope, srid_val;
    END IF;

    RETURN COALESCE(water_tile, ''::bytea) || COALESCE(forest_tile, ''::bytea) || COALESCE(build_tile, ''::bytea) || COALESCE(limit_tile, ''::bytea);
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE;

-- 4. H3 Hexagonal Purpose Travel Demand MVT Function
CREATE OR REPLACE FUNCTION public.mvt_h3(
    z integer, x integer, y integer, query_params json DEFAULT NULL
) RETURNS bytea AS $$
DECLARE
    envelope geometry := ST_TileEnvelope(z, x, y);
    scenario text := COALESCE(query_params->>'scenario', 'santchil_baseline');
    tbl_name text := scenario || '_h3';
    srid_val integer;
    tol float;
    result bytea;
    table_exists boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = tbl_name
    ) INTO table_exists;

    IF NOT table_exists THEN
        RETURN ''::bytea;
    END IF;

    BEGIN
        EXECUTE format('SELECT COALESCE(NULLIF(ST_SRID(geometry), 0), 32719) FROM %I LIMIT 1', tbl_name) INTO srid_val;
    EXCEPTION WHEN OTHERS THEN
        srid_val := 32719;
    END;
    IF srid_val IS NULL OR srid_val = 0 THEN
        srid_val := 32719;
    END IF;

    tol := CASE 
        WHEN z < 10 THEN 40.0
        WHEN z < 12 THEN 15.0
        WHEN z < 14 THEN 4.0
        ELSE 0.0
    END;

    EXECUTE format('
        WITH bounds AS (
            SELECT ST_Transform($1, $4) AS geom_native
        ),
        hexes AS (
            SELECT 
                h.h3_index,
                COALESCE(h.od_flow, 0)::float8 AS od_flow,
                COALESCE(h.trips_work, 0)::float8 AS trips_work,
                COALESCE(h.trips_study, 0)::float8 AS trips_study,
                COALESCE(h.trips_shopping, 0)::float8 AS trips_shopping,
                COALESCE(h.trips_personal, 0)::float8 AS trips_personal,
                COALESCE(h.trips_recreational, 0)::float8 AS trips_recreational,
                COALESCE(h.trips_returning_home, 0)::float8 AS trips_returning_home,
                COALESCE(h.pop_total, 0)::float8 AS pop_total,
                CASE 
                    WHEN $3 > 0 THEN ST_Simplify(h.geometry, $3)
                    ELSE h.geometry 
                END AS geom
            FROM %I h, bounds b
            WHERE h.geometry && b.geom_native
        )
        SELECT ST_AsMVT(tile, ''h3'', 4096, ''geom'')
        FROM (
            SELECT 
                h3_index, od_flow, trips_work, trips_study, trips_shopping,
                trips_personal, trips_recreational, trips_returning_home, pop_total,
                ST_AsMVTGeom(ST_Transform(geom, 3857), $1, 4096, 64, true) AS geom
            FROM hexes
            WHERE geom IS NOT NULL
        ) tile;', tbl_name)
    INTO result
    USING envelope, z, tol, srid_val;

    RETURN result;
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE;
