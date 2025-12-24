-- Create temporary table with intersected geometry
drop table if exists h3_ciclo_inter;
create temp table h3_ciclo_inter as
select
	h3.id as id_hex,
	ciclo."PHANTO",
	ciclo.proyect,
	ciclo.op_ci,
	ciclo.op_cr,
	ciclo."CICLOVIA_N",
	st_intersection(ciclo.geometry,h3.geometry) as geometry
from
	{ciclo_table} ciclo,
	{h3_table} h3
where
	st_intersects(ciclo.geometry,h3.geometry) = TRUE
ORDER BY id_hex;

-- ci_total	--	
ALTER TABLE {h3_table}
ADD COLUMN if not exists ci_total float;

update {h3_table}
set ci_total = subquery.ci_total
FROM (
	SELECT
		id_hex,
		sum(st_length(geometry)) as ci_total
	FROM
		h3_ciclo_inter
	group by id_hex
) as subquery
where {h3_table}.id = subquery.id_hex;

-- fantom --
ALTER TABLE {h3_table}
ADD COLUMN if not exists fantom float;

update {h3_table}
set fantom = subquery.fantom 
FROM (
	SELECT
		id_hex,
		sum(st_length(geometry)) as fantom
	FROM
		h3_ciclo_inter
	where h3_ciclo_inter."PHANTO" = 1
	group by id_hex
) as subquery
where {h3_table}.id = subquery.id_hex;

-- project = 1 --
ALTER TABLE {h3_table}
ADD COLUMN if not exists project_1 float;

update {h3_table}
set project_1 = subquery.project_1 
FROM (
	SELECT
		id_hex,
		sum(st_length(geometry)) as project_1
	FROM
		h3_ciclo_inter
	where h3_ciclo_inter.proyect = 1
	group by id_hex
) as subquery
where {h3_table}.id = subquery.id_hex;

-- project = 2
ALTER TABLE {h3_table}
ADD COLUMN if not exists project_2 float;

update {h3_table}
set project_2 = subquery.project_2 
FROM (
	SELECT
		id_hex,
		sum(st_length(geometry)) as project_2
	FROM
		h3_ciclo_inter
	where h3_ciclo_inter.proyect = 2
	group by id_hex
) as subquery
where {h3_table}.id = subquery.id_hex;

-- ci_b => o_op_ci = 0
ALTER TABLE {h3_table}
ADD COLUMN if not exists ci_b float;

update {h3_table}
set ci_b = subquery.ci_b 
FROM (
	SELECT
		id_hex,
		sum(st_length(geometry)) as ci_b
	FROM
		h3_ciclo_inter
	where h3_ciclo_inter.op_ci = 0
	group by id_hex
) as subquery
where {h3_table}.id = subquery.id_hex;

-- ci_m => o_op_ci = 1
ALTER TABLE {h3_table}
ADD COLUMN if not exists ci_m float;

update {h3_table}
set ci_m = subquery.ci_m 
FROM (
	SELECT
		id_hex,
		sum(st_length(geometry)) as ci_m
	FROM
		h3_ciclo_inter
	where h3_ciclo_inter.op_ci = 1
	group by id_hex
) as subquery
where {h3_table}.id = subquery.id_hex;

-- cr_b => op_cr = 0
ALTER TABLE {h3_table}
ADD COLUMN if not exists cr_b float;

update {h3_table}
set cr_b = subquery.cr_b 
FROM (
	SELECT
		id_hex,
		sum(st_length(geometry)) as cr_b
	FROM
		h3_ciclo_inter
	where h3_ciclo_inter.op_cr = 0
	group by id_hex
) as subquery
where {h3_table}.id = subquery.id_hex;

-- cr_m => op_cr = 1
ALTER TABLE {h3_table}
ADD COLUMN if not exists cr_m float;

update {h3_table}
set cr_m = subquery.cr_m 
FROM (
	SELECT
		id_hex,
		sum(st_length(geometry)) as cr_m
	FROM
		h3_ciclo_inter
	where h3_ciclo_inter.op_cr = 1
	group by id_hex
) as subquery
where {h3_table}.id = subquery.id_hex;

-- Temporary table for length of each CICLOVIA_N
drop table if exists length_ciclovia_n;
create temp table length_ciclovia_n as
select
	ciclo."CICLOVIA_N",
	ciclo.op_ci,
	sum(st_length(ciclo.geometry)) as ciclo_n_len
FROM
	public.{ciclo_table} ciclo
group by ciclo."CICLOVIA_N",ciclo.op_ci
order by ciclo."CICLOVIA_N";

ALTER TABLE {h3_table}
ADD COLUMN if not exists ci_n_b float;

-- ci_n_b => op_ci = 0
update {h3_table}
set ci_n_b = subquery.ci_n_b
FROM(
	SELECT
		id_hex,
		sum(length_ciclovia_n.ciclo_n_len) as ci_n_b
	FROM
		h3_ciclo_inter,
		length_ciclovia_n
	where
		h3_ciclo_inter."CICLOVIA_N" = length_ciclovia_n."CICLOVIA_N" and h3_ciclo_inter.op_ci = 0
	group by id_hex
	order by id_hex
) as subquery
where {h3_table}.id = subquery.id_hex;

ALTER TABLE {h3_table}
ADD COLUMN if not exists ci_n_m float;

-- ci_n_m => op_ci = 1
update {h3_table}
set ci_n_m = subquery.ci_n_m
FROM(
	SELECT
		id_hex,
		sum(length_ciclovia_n.ciclo_n_len) as ci_n_m
	FROM
		h3_ciclo_inter,
		length_ciclovia_n
	where
		h3_ciclo_inter."CICLOVIA_N" = length_ciclovia_n."CICLOVIA_N" and h3_ciclo_inter.op_ci = 1
	group by id_hex
	order by id_hex
) as subquery
where {h3_table}.id = subquery.id_hex;