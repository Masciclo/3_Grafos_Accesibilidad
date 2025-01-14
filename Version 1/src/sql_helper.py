import psycopg2
import geopandas as gpd
from psycopg2.sql import SQL, Identifier


def test_database_connection(db, host, port, usr, passw):
    try:
        conn = psycopg2.connect(
            dbname=db,
            host=host,
            port=port,
            user=usr,
            password=passw
        )
        print("Database Connected!")
        return conn
    except:
        print("Unable to connect to Database.")
        return None


def import_shape_to_database(shp, db, conn):
    shp.to_postgis(db, conn, if_exists="replace")


def check_table_existence(table, conn):
    with conn.cursor() as cur:
        cur.execute(f"SELECT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = '{table}');")
        return cur.fetchone()[0]


def create_and_clean_topology(shp, topo_name, srid, conn, geometry):
    init_time = pd.Timestamp.now()
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT topology.CreateTopology('{topo_name}', {srid}); "
            f"SELECT topology.AddTopoGeometryColumn('{topo_name}', 'public', '{shp}', 'topo_geom', 'LINESTRING'); "
            f"UPDATE {shp} SET topo_geom = topology.toTopoGeom({geometry}, '{topo_name}', 1, 0.001);"
        )
    finish_time = pd.Timestamp.now()
    print("Tiempo empleado en cortar la topología:")
    print(finish_time - init_time)


def create_buffer(lista_shps, metros, conn):
    collapse_shps_names = "_".join(lista_shps)
    buffer_name = f"{collapse_shps_names}_{metros}"
    index_name = f"{buffer_name}_idx"
    table_existence = check_table_existence(buffer_name, conn)

    if table_existence:
        print(f"Cargando buffer {buffer_name}")
        with conn.cursor() as cur:
            cur.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON buffers.{buffer_name} USING GIST (geometry);")
        return buffer_name
    else:
        if metros != 0:
            print("Creando buffer")
            buffer_sql = " union all ".join(
                [f"SELECT ST_Union(ST_Buffer(\"{x}\".geometry, {metros})) as geometry FROM public.\"{x}\" " for x in lista_shps]
            )
            with conn.cursor() as cur:
                cur.execute(
                    f"CREATE SCHEMA IF NOT EXISTS buffers; "
                    f"CREATE TABLE buffers.{buffer_name} AS {buffer_sql}; "
                    f"CREATE INDEX {index_name} ON buffers.{buffer_name} USING GIST (geometry);"
                )
            return buffer_name
        else:
            return False


def buffer_difference(nombre_resultado, buffer_inhibidores, buffer_desinhibidores, conn):
    with conn.cursor() as cur:
        cur.execute(
            f"CREATE TABLE IF NOT EXISTS buffers.bf_{nombre_resultado} AS "
            f"SELECT "
            f"ST_Difference(bi.geometry, bd.geometry) AS geometry "
            f"FROM buffers.{buffer_inhibidores} bi, buffers.{buffer_desinhibidores} bd; "
            f"CREATE INDEX IF NOT EXISTS idx_bf_{nombre_resultado} "
            f"ON buffers.bf_{nombre_resultado} USING GIST(geometry);"
        )
    return f"bf_{nombre_resultado}"