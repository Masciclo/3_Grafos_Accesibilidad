drop table if exists h3_components_inter;
create temp table h3_components_inter as
select
	h3.h3_index as id_hex,
	components.component,
	st_intersection(components.the_geom,h3.geometry) as geometry
from
	{component_table} components,
	{h3_table} h3
where
	st_intersects(components.the_geom,h3.geometry) = TRUE
ORDER BY id_hex;

-- Ensure columns exist in the target table
ALTER TABLE {h3_table} ADD COLUMN IF NOT EXISTS m_comp integer;
ALTER TABLE {h3_table} ADD COLUMN IF NOT EXISTS comp_total float;

-- Aggregating predominant component and total length per hexagon
WITH components_length AS (
    SELECT 
        id_hex, 
        component, 
        SUM(ST_Length(geometry)) as component_length
    FROM h3_components_inter
    GROUP BY id_hex, component
),
predominant_components AS (
    SELECT DISTINCT ON (id_hex)
        id_hex, 
        component as predominant_component
    FROM components_length
    ORDER BY id_hex, component_length DESC
)
UPDATE {h3_table}
SET m_comp = subquery.comp_intersect,
    comp_total = subquery.comp_total
FROM (
    SELECT 
        pc.id_hex, 
        pc.predominant_component AS comp_intersect,
    	cl.component_length AS comp_total
    FROM predominant_components pc
    JOIN components_length cl ON pc.predominant_component = cl.component AND pc.id_hex = cl.id_hex
) as subquery
where {h3_table}.h3_index = subquery.id_hex;
