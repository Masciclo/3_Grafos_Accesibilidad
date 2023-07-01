# Python version of +ciclo
+Ciclo python version is a python application for processing GIS information to get insight related to bicycle path in any city of the world.
This app use PostgreSQL with PostGIS and PgRouting libraries as a database running in docker. 

TODO: 
-- [ignacio] Mantener indice unico y general para filtrar mas adelante.
-- [Pedro/ignacio] incluir filtro en parámetros de entrada / cambiar create_full_network .
-- [ignacio] Estandarizar geoms.
-- [ignacio] accesibilidad.
-- [Pedro] incorporar el location a los parámetros de entrada 
-- [Pedro] modificar flujo de main
    -- [ignacio] modificar querys 
    -- [Pedro] inhibir osm antes de unir con ciclos
-- [Pedro/ignacio] parametrizar srid python/sql srid

-- [] agregar srid a hexágonos