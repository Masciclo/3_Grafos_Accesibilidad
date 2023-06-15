-- Si no existe, crea un esquema llamado 'buffers'
CREATE SCHEMA IF NOT EXISTS buffers;

-- Comprueba si la tabla existe
DO
$$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'buffers' AND tablename = '{buffer_name}') THEN
        -- Si metros no es igual a 0, crear la tabla de buffers y su correspondiente índice
        IF {metros} != 0 THEN
            CREATE TABLE buffers.{buffer_name} AS (
                {buffer_sql}
            );
            CREATE INDEX {index_name} ON buffers.{buffer_name} USING GIST (geometry);
        END IF;
    ELSE
        -- Si la tabla ya existe, crea el índice si no existe
        CREATE INDEX IF NOT EXISTS {index_name} ON buffers.{buffer_name} USING GIST (geometry);
    END IF;
END
$$;
