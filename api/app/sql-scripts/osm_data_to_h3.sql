-- Create temporary table with intersected geometry
drop table if exists h3_osm_inter;
create temp table h3_osm_inter as
select
	h3.id as id_hex,
	st_intersection(osm.geometry,h3.geometry) as geometry
from
	{osm_table} osm,
	{h3_table} h3
where
	st_intersects(osm.geometry,h3.geometry) = TRUE
ORDER BY id_hex;

alter table {h3_table}
add column if not exists m_osm float;

update {h3_table}
set m_osm = subquery.m_osm
FROM (
	SELECT
		id_hex,
		sum(st_length(geometry)) as m_osm
	FROM
		h3_osm_inter
	group by id_hex
) as subquery
where {h3_table}.id = subquery.id_hex;