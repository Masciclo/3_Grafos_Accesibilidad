CREATE INDEX IF NOT EXISTS {layer_name}_geom_idx 
ON {schema_name}.{layer_name} 
USING GIST (geometry);