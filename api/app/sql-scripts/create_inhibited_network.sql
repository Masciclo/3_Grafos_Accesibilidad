DROP TABLE IF EXISTS network_with_impedance;
CREATE TEMP TABLE network_with_impedance AS
SELECT 
    (ST_Dump(ST_MakeValid(ST_Intersection(a.geometry, b.geometry)))).geom AS geometry,
    COALESCE(b.impedance, a.impedance) AS impedance
FROM 
    {network_table} a
    LEFT JOIN buffers.{impedance_buffer} b 
    ON ST_Intersects(a.geometry, b.geometry);

CREATE INDEX network_with_impedance_gix ON network_with_impedance USING GIST (geometry);

drop table if EXISTS network_without_impedance;
create TEMP table network_without_impedance AS
select
	(ST_Dump(ST_MakeValid(st_difference(a.geometry,b.geometry)))).geom AS geometry,
	1 as impedance
FROM
	{network_table} a,
	buffers.{inhib_buffer} b;

CREATE INDEX network_without_impedance_gix ON network_without_impedance USING GIST (geometry);

DROP TABLE IF EXISTS {result_name};
CREATE TABLE {result_name} AS
SELECT 
    geometry,
    impedance
FROM (
    SELECT * FROM network_with_impedance
    UNION ALL
    SELECT * FROM network_without_impedance
) sub
WHERE geometry IS NOT NULL 
  AND ST_GeometryType(geometry) = 'ST_LineString'
  AND ST_Length(geometry) > 0.0001;
