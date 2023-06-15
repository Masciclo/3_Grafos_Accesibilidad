BEGIN;

SELECT topology.CreateTopology('{topo_name}', {srid});
SELECT topology.AddTopoGeometryColumn('{topo_name}', 'public', '{shp}', 'topo_geom', 'LINESTRING');
UPDATE "{shp}" SET topo_geom = topology.toTopoGeom('{geometry}', '{topo_name}', 1, 0.001);

COMMIT;
