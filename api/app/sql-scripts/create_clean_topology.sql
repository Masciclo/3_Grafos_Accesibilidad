-- Crear el esquema si no existe
CREATE SCHEMA IF NOT EXISTS topology;

-- Crear la topología
SELECT topology.CreateTopology('{topo}', {srid});

-- Agregar una columna de topología a tu tabla
SELECT topology.AddTopoGeometryColumn('{topo}', 'public', '{table}', 'topogeom', 'LINESTRING');

-- Llenar la columna de topología con los datos de tu tabla
UPDATE public.{table}
SET topogeom = topology.toTopoGeom(geometry, '{topo}', 1);

