CREATE TABLE IF NOT EXISTS public.{desinhibitor_name} AS 
  
-- Uniendo las dos tablas en una sola consulta
SELECT 
    geometry 
FROM {ciclo_table}
UNION ALL
SELECT 
    geometry 
FROM {desinhibitor_table}
{filters};
