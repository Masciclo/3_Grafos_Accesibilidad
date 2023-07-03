-- Add impedance field
alter table {table_name}
add column impedance float;

-- impedance for each type of highway
UPDATE {table_name}
SET impedance = CASE
    WHEN highway = 'primary' THEN 3
    WHEN highway = 'secondary' THEN 2
    WHEN highway = 'tertiary' THEN 1.5
    ELSE 1
END;

--Create buffer for each type of highway
CREATE TEMP TABLE primary_buffer AS
SELECT st_union(ST_Buffer(geometry, {dist_buffer})) AS geometry, impedance
FROM {table_name}
where highway = 'primary'
group by impedance;
CREATE INDEX primary_buffer_gix ON primary_buffer USING GIST (geometry);

CREATE TEMP TABLE secondary_buffer AS
SELECT st_union(ST_Buffer(geometry, {dist_buffer})) AS geometry, impedance
FROM {table_name}
where highway = 'secondary'
group by impedance;
CREATE INDEX secondary_buffer_gix ON secondary_buffer USING GIST (geometry);

CREATE TEMP TABLE tertiary_buffer AS
SELECT st_union(ST_Buffer(geometry, {dist_buffer})) AS geometry, impedance
FROM {table_name}
where highway = 'tertiary'
group by impedance;
CREATE INDEX tertiary_buffer_gix ON tertiary_buffer USING GIST (geometry);

-- clip between both buffers
UPDATE secondary_buffer 
SET geometry = ST_Difference(secondary_buffer.geometry, primary_buffer.geometry)
FROM primary_buffer
WHERE ST_Intersects(secondary_buffer.geometry, primary_buffer.geometry);

UPDATE tertiary_buffer 
SET geometry = ST_Difference(tertiary_buffer.geometry, primary_buffer.geometry)
FROM primary_buffer
WHERE ST_Intersects(tertiary_buffer.geometry, primary_buffer.geometry);

-- update the geometry of the buffers
UPDATE tertiary_buffer 
SET geometry = ST_Difference(tertiary_buffer.geometry, secondary_buffer.geometry)
FROM secondary_buffer
WHERE ST_Intersects(tertiary_buffer.geometry, secondary_buffer.geometry);

-- create final buffer
CREATE TABLE {result_table} AS 
SELECT * FROM primary_buffer
UNION ALL
SELECT * FROM secondary_buffer
WHERE geometry IS NOT NULL
UNION ALL
SELECT * FROM tertiary_buffer
WHERE geometry IS NOT NULL;

CREATE INDEX {result_table}_gix ON {result_table} USING GIST (geometry);