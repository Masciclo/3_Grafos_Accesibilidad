CREATE OR REPLACE FUNCTION shortest_path_distance(
    _table_name TEXT, -- Nombre de la tabla que contiene la red de transporte
    _source INTEGER, -- Nodo de inicio para el cálculo de la ruta más corta
    _target INTEGER, -- Nodo final para el cálculo de la ruta más corta
    _distance_column TEXT, -- Nombre de la columna que se utilizará para calcular las distancias
    _directed BOOLEAN -- Si la red es dirigida o no
)
RETURNS DOUBLE PRECISION AS $$
DECLARE
    result DOUBLE PRECISION; -- Variable que almacenará el resultado
BEGIN
    -- El uso de la función format() y %I, %L evita la inyección SQL
    EXECUTE format('
        SELECT SUM(pt_agg.agg_cost)
        FROM pgr_dijkstra(
            ''SELECT id, source, target, %I AS cost FROM %I'',
            %L,
            %L,
            directed := %L
        ) AS pt_agg;
    ', _distance_column, _table_name, _source, _target, _directed) INTO result;

    RETURN result; -- Retorna el resultado del cálculo
END;
$$ LANGUAGE plpgsql;
