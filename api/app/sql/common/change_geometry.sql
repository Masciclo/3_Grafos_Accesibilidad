ALTER TABLE {table_name} 
  ALTER COLUMN geometry 
  TYPE Geometry({geom_type}, {srid}) 
  USING ST_Transform(geometry, {srid});