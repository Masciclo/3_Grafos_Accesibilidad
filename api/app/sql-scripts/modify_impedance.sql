-- Add impedance field if it does not already exist
ALTER TABLE {table_name}
ADD COLUMN IF NOT EXISTS impedance float;

-- Update impedance for each type of highway
UPDATE {table_name}
SET impedance = CASE
    WHEN highway = 'primary' THEN 1
    WHEN highway = 'secondary' THEN 1
    WHEN highway = 'tertiary' THEN 1
    ELSE 1
END;
