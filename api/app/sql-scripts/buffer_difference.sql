CREATE TABLE IF NOT EXISTS buffers.{inhib_name} AS 
SELECT 
    ST_Difference(bi.geometry, bd.geometry) AS geometry 
FROM buffers.{buffer_inhibitor} bi, 
    buffers.{buffer_desinhibitor} bd; 

CREATE INDEX IF NOT EXISTS idx_{inhib_name} 
ON buffers.{inhib_name} USING GIST(geometry);

CREATE TABLE IF NOT EXISTS buffers.{impedance_name} AS 
SELECT 
    ST_Difference(bi.geometry, bd.geometry) AS geometry 
FROM buffers.{buffer_impedance} bi, 
    buffers.{buffer_desinhibitor} bd; 

CREATE INDEX IF NOT EXISTS idx_{impedance_name} 
ON buffers.{impedance_name} USING GIST(geometry);
