-- census_data_to_h3.sql
-- Phase 5: Normalizes population from census blocks to H3 cells using Mass Conservation.

-- 1. Create temporary table with intersections
DROP TABLE IF EXISTS h3_census_inter;
CREATE TEMP TABLE h3_census_inter AS
SELECT
    h3.h3_index AS id_hex,
    c.pop_total,
    ST_Area(ST_Intersection(c.geometry, h3.geometry)) AS intersection_area,
    ST_Area(c.geometry) AS total_block_area
FROM
    {census_table} c,
    {h3_table} h3
WHERE
    ST_Intersects(c.geometry, h3.geometry) = TRUE;

-- 2. Add column to master H3 table
ALTER TABLE {h3_table} ADD COLUMN IF NOT EXISTS pop_total FLOAT DEFAULT 0;

-- 3. Update using Mass Conservation Algorithm
-- Pop_hex = Sum( Pop_block * (Intersection_Area / Total_Block_Area) )
UPDATE {h3_table}
SET pop_total = subquery.total_pop
FROM (
    SELECT
        id_hex,
        SUM(pop_total * (intersection_area / NULLIF(total_block_area, 0))) AS total_pop
    FROM
        h3_census_inter
    GROUP BY id_hex
) AS subquery
WHERE {h3_table}.h3_index = subquery.id_hex;

-- 4. Audit
DO $$
BEGIN
    RAISE NOTICE 'Census population normalization completed.';
END $$;
