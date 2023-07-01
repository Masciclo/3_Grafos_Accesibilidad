# Python version of +ciclo
+Ciclo python version is a python application for processing GIS information to get insight related to bicycle path in any city of the world.
This app use PostgreSQL with PostGIS and PgRouting libraries as a database running in docker. 

TODO: 
-- [ignacio] Mantener indice unico y general para filtrar mas adelante.
-- [Pedro/ignacio] testear filtros (create full network).
-- [ignacio] Estandarizar geoms.
-- [ignacio] accesibilidad.
-- [Pedro] testear osm para vias principales, ver que hacer con otros tipos de caminos 
-- [Pedro] modificar flujo de main
    -- [ignacio] modificar querys 
    -- [Pedro] inhibir osm antes de unir con ciclos
-- [Pedro/ignacio] parametrizar srid python/sql srid

-- [] agregar srid a hexágonos