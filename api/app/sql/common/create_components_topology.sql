DO $$ 
BEGIN
  BEGIN
    PERFORM topology.DropTopology('{topo}');
  EXCEPTION
    WHEN SQLSTATE 'P0001' THEN -- catch specific exception when topology doesn't exist
    NULL; -- take no action
  END;
END $$;

-- Crear el esquema si no existe
CREATE SCHEMA IF NOT EXISTS topology;

CREATE TABLE IF NOT EXISTS {result_name} AS
select
    *
from
    {table}
where
    impedance =< 1;


-- Crear la topología
SELECT topology.CreateTopology('{result_name}', {srid});

-- Agregar una columna de topología a tu tabla
SELECT topology.AddTopoGeometryColumn('{result_name}', 'public', '{table}', 'topogeom', 'LINESTRING');

-- Llenar la columna de topología con los datos de tu tabla
UPDATE public.{table}
SET topogeom = topology.toTopoGeom(geometry, '{result_name}', 1);
