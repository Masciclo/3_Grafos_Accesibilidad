-- Add impedance field if it does not already exist
alter table {table_name}
ADD COLUMN IF NOT EXISTS impedance float,
ADD COLUMN IF NOT EXISTS highway text,
ADD COLUMN IF NOT EXISTS type text;

-- impedance for each type of highway
UPDATE {table_name}
SET impedance = CASE
    WHEN is_project = TRUE THEN 1.0 -- Prevent overriding project proposal impedance
    WHEN COALESCE(highway, type) = 'primary' THEN {high_impedance}
    WHEN COALESCE(highway, type) = 'secondary' THEN {medium_impedance}
    WHEN COALESCE(highway, type) = 'tertiary' THEN {low_impedance}
    ELSE {else_impedance}
END;

-- If not exists, create a new schema called buffers
CREATE SCHEMA IF NOT EXISTS buffers;

--Create buffer for each type of highway
CREATE TEMP TABLE primary_buffer AS
SELECT st_union(ST_Buffer(geometry, {dist_buffer})) AS geometry, impedance
FROM {table_name}
where COALESCE(highway, type) = 'primary'
group by impedance;
CREATE INDEX primary_buffer_gix ON primary_buffer USING GIST (geometry);

CREATE TEMP TABLE secondary_buffer AS
SELECT st_union(ST_Buffer(geometry, {dist_buffer})) AS geometry, impedance
FROM {table_name}
where COALESCE(highway, type) = 'secondary'
group by impedance;
CREATE INDEX secondary_buffer_gix ON secondary_buffer USING GIST (geometry);

CREATE TEMP TABLE tertiary_buffer AS
SELECT st_union(ST_Buffer(geometry, {dist_buffer})) AS geometry, impedance
FROM {table_name}
where COALESCE(highway, type) = 'tertiary'
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


DROP TABLE IF EXISTS buffers.{result_table};

-- create final buffer
-- Subdivide the final polygons to improve spatial join performance in later stages
CREATE TABLE buffers.{result_table} AS 
WITH unioned AS (
    SELECT * FROM primary_buffer
    UNION ALL
    SELECT * FROM secondary_buffer
    WHERE geometry IS NOT NULL
    UNION ALL
    SELECT * FROM tertiary_buffer
    WHERE geometry IS NOT NULL
)
SELECT impedance, ST_Subdivide(geometry) as geometry FROM unioned;

CREATE INDEX {result_table}_gix ON buffers.{result_table} USING GIST (geometry);