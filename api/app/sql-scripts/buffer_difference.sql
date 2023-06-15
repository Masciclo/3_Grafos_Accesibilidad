CREATE TABLE IF NOT EXISTS buffers.bf_{nombre_resultado} AS 
SELECT 
ST_Difference(bi.geometry, bd.geometry) AS geometry 
FROM buffers.{buffer_inhibidores} bi, buffers.{buffer_desinhibidores} bd; 

CREATE INDEX IF NOT EXISTS idx_bf_{nombre_resultado} 
ON buffers.bf_{nombre_resultado} USING GIST(geometry);
