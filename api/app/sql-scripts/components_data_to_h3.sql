drop table if exists h3_components_inter;
create temp table h3_components_inter as
select
	h3.id as id_hex,
	components.component,
	st_intersection(components.the_geom,h3.geometry) as geometry
from
	{component_table} components,
	{h3_table} h3
where
	st_intersects(components.the_geom,h3.geometry) = TRUE
ORDER BY id_hex;

drop table if exists components_length;
create temp table components_length as
select
	component,
	sum(st_length(the_geom)) as component_length
from
	{component_table} components
group by component
order by component;

alter table {h3_table}
add column if not exists {result_table}_component int,
add column if not exists {result_table}_comp_intersect float,
add column if not exists {result_table}_comp_total float;

update {h3_table}
set {result_table}_component = subquery.component,
{result_table}_comp_intersect = subquery.comp_intersect,
{result_table}_comp_total = subquery.comp_total
FROM (
    WITH component_intersections AS (
    	SELECT
    		id_hex,
    		component,
    		sum(st_length(geometry)) as intersection_length
    	FROM
    		h3_components_inter
    	GROUP BY id_hex, component
    ),
    ranked_components AS (
    	SELECT
    		*,
    		ROW_NUMBER() OVER(PARTITION BY id_hex ORDER BY intersection_length DESC) as rn
    	FROM component_intersections
    ),
    predominant_components AS (
    	SELECT
    		id_hex,
    		component AS predominant_component,
    		intersection_length AS predominant_component_length
    	FROM ranked_components
    	WHERE rn = 1
    )
    SELECT
    	pc.id_hex,
    	pc.predominant_component as component,
    	pc.predominant_component_length as comp_intersect,
    	cl.component_length AS comp_total
    FROM predominant_components pc
    JOIN components_length cl ON pc.predominant_component = cl.component
    ORDER BY id_hex
) as subquery
where {h3_table}.id = subquery.id_hex;

