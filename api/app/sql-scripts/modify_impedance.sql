-- Add impedance field
alter table {table_name}
add column impedance float;

-- impedance for each type of highway
UPDATE {table_name}
SET impedance = CASE
    WHEN highway = 'primary' THEN 1
    WHEN highway = 'secondary' THEN 1
    WHEN highway = 'tertiary' THEN 1
    ELSE 1
END;