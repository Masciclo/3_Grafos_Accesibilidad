-- demand_data_to_h3.sql
-- Phase 6: Aggregates OD Flow from the network into the H3 grid.

-- 1. Create temporary table with intersected geometry and flow
drop table if exists h3_demand_inter;
create temp table h3_demand_inter as
select
	h3.h3_index as id_hex,
	n.od_flow,
	st_length(st_intersection(n.geometry,h3.geometry)) as seg_len,
	st_length(n.geometry) as total_len
from
	{network_table} n,
	{h3_table} h3
where
	n.od_flow > 0
	AND st_intersects(n.geometry,h3.geometry) = TRUE;

-- 2. Add columns to master H3 table
alter table {h3_table} add column if not exists od_flow float default 0;

-- 3. Update using weighted length
-- Hex.Flow = Sum( Edge.Flow * (Length_in_Hex / Total_Edge_Length) )
update {h3_table}
set od_flow = subquery.total_flow
FROM (
	SELECT
		id_hex,
		sum(od_flow * (seg_len / NULLIF(total_len, 0))) as total_flow
	FROM
		h3_demand_inter
	group by id_hex
) as subquery
where {h3_table}.h3_index = subquery.id_hex;
