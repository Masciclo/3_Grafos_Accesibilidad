CREATE TABLE IF NOT EXISTS buffers.bf_{result_name} AS 
SELECT 
    ST_Difference(bi.geometry, bd.geometry) AS geometry 
FROM buffers.{buffer_inhibitor} bi, 
    buffers.{buffer_desinhibitor} bd; 

CREATE INDEX IF NOT EXISTS idx_bf_{result_name} 
ON buffers.bf_{result_name} USING GIST(geometry);
