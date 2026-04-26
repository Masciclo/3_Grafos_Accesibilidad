drop table if exists h3_ciclo_inter;
create temp table h3_ciclo_inter as
select
	h3.id as id_hex,
	st_intersection(ciclo.geometry,h3.geometry) as geometry
from
	{ciclo_table} ciclo,
	{h3_table} h3
where
	st_intersects(ciclo.geometry,h3.geometry) = TRUE;

-- Agregamos columnas de métricas a la tabla H3
alter table {h3_table}
add column if not exists total_ciclo_km float,
add column if not exists phanto_ciclo_km float;

-- Actualizamos el total de ciclovías por hexágono (Universal)
update {h3_table}
set total_ciclo_km = sub.total_km
from (
    select id_hex, sum(st_length(geometry))/1000 as total_km
    from h3_ciclo_inter
    group by id_hex
) as sub
where {h3_table}.id = sub.id_hex;

-- Cálculo de PHANTO (Condicional): Solo si la columna existe (Compatibilidad Santiago)
DO $$ 
BEGIN 
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = '{ciclo_table}' AND column_name = 'PHANTO') THEN
        EXECUTE format('
            UPDATE {h3_table}
            SET phanto_ciclo_km = sub.p_km
            FROM (
                SELECT h3.id as id_hex, sum(st_length(st_intersection(c.geometry, h3.geometry)))/1000 as p_km
                FROM {ciclo_table} c, {h3_table} h3
                WHERE st_intersects(c.geometry, h3.geometry) AND c."PHANTO" = 1
                GROUP BY h3.id
            ) as sub
            WHERE {h3_table}.id = sub.id_hex');
    END IF;
END $$;
