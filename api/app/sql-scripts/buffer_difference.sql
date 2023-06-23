CREATE TABLE IF NOT EXISTS buffers.{result_name} AS 
SELECT 
    ST_Difference(bi.geometry, bd.geometry) AS geometry 
FROM buffers.{buffer_inhibitor} bi, 
    buffers.{buffer_desinhibitor} bd; 

CREATE INDEX IF NOT EXISTS idx_{result_name} 
ON buffers.{result_name} USING GIST(geometry);
