DROP TABLE IF EXISTS network_with_impedance;
CREATE TEMP TABLE network_with_impedance AS
SELECT 
    (ST_Dump(ST_Intersection(a.geometry, b.geometry))).geom AS geometry,
    COALESCE(b.impedance, a.impedance) AS impedance
FROM 
    {network_table} a
    LEFT JOIN buffers.{impedance_buffer} b 
    ON ST_Intersects(a.geometry, b.geometry);

-- Create spatial index
CREATE INDEX network_with_impedance_gix ON network_with_impedance USING GIST (geometry);

drop table if EXISTS network_without_impedance;
create TEMP table network_without_impedance AS
select
	st_difference(a.geometry,b.geometry),
	1 as impedance
FROM
	{network_table} a,
	buffers.{inhib_buffer} b;
-- Create spatial index
CREATE INDEX IF NOT EXISTS network_with_impedance_gix ON network_with_impedance USING GIST (geometry);

DROP TABLE IF EXISTS {result_name};
CREATE TABLE {result_name} AS
SELECT * FROM network_with_impedance
UNION ALL
SELECT * FROM network_without_impedance;