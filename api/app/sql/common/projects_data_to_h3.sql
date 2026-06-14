-- projects_data_to_h3.sql
-- Phase 5: Aggregates project length from proposed infrastructure to H3 cells.

-- 1. Create temporary table with intersected geometry
drop table if exists h3_projects_inter;
create temp table h3_projects_inter as
select
	h3.h3_index as id_hex,
	st_intersection(p.geometry,h3.geometry) as geometry
from
	{projects_table} p,
	{h3_table} h3
where
    p.geometry && h3.geometry
	AND st_intersects(p.geometry,h3.geometry) = TRUE;

-- 2. Add column to master H3 table
alter table {h3_table} add column if not exists m_project float default 0;

-- 3. Update using length
update {h3_table}
set m_project = subquery.m_proj
FROM (
	SELECT
		id_hex,
		sum(st_length(geometry)) as m_proj
	FROM
		h3_projects_inter
	group by id_hex
) as subquery
where {h3_table}.h3_index = subquery.id_hex;
