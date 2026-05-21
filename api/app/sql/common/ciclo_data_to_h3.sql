-- Create temporary table with intersected geometry
drop table if exists h3_ciclo_inter;
create temp table h3_ciclo_inter as
select
	h3.h3_index as id_hex,
	st_intersection(ciclo.geometry,h3.geometry) as geometry
from
	{ciclo_table} ciclo,
	{h3_table} h3
where
	st_intersects(ciclo.geometry,h3.geometry) = TRUE
ORDER BY id_hex;

alter table {h3_table}
add column if not exists m_ciclo float;

update {h3_table}
set m_ciclo = subquery.m_ciclo
FROM (
	SELECT
		id_hex,
		sum(st_length(geometry)) as m_ciclo
	FROM
		h3_ciclo_inter
	group by id_hex
) as subquery
where {h3_table}.h3_index = subquery.id_hex;
