import sys
import os
import geopandas as gpd
from shapely.geometry import LineString
from sqlalchemy import create_engine
from infra.database import df_to_postgres, create_conn
from ui.components import diagnostic_handler

def test_ingestion():
    print("🚀 Starting Database Ingestion Test...")
    
    # DB Credentials from environment or defaults
    DATABASE_NAME = os.getenv('DATABASE_NAME', 'ciclo_dev')
    HOST = os.getenv('HOST', 'stationdb')
    PORT = os.getenv('PORT', '5432')
    USER = os.getenv('DB_USER', 'ciclo')
    PASSWORD = os.getenv('DB_PASSWORD', 'ciclo')
    
    # 1. Create a dummy GeoDataFrame
    data = {
        'id': [1, 2],
        'highway': ['residential', 'primary'],
        'geometry': [
            LineString([(0, 0), (1, 1)]),
            LineString([(1, 1), (2, 2)])
        ]
    }
    gdf = gpd.GeoDataFrame(data, crs="EPSG:32718")
    
    # 2. Test Case A: Using raw engine parameters (no conn)
    try:
        print("\n--- Test Case A: Engine from Params ---")
        df_to_postgres(gdf, "test_ingestion_a", "LINESTRING", 32718, USER, PASSWORD, HOST, PORT, DATABASE_NAME)
        print("✅ Test Case A passed.")
    except Exception as e:
        print(f"❌ Test Case A failed: {str(e)}")
        sys.exit(1)

    # 3. Test Case B: Using a psycopg2 connection (The Shared Connection scenario)
    try:
        print("\n--- Test Case B: Psycopg2 Connection ---")
        conn = create_conn(DATABASE_NAME, HOST, PORT, USER, PASSWORD)
        df_to_postgres(gdf, "test_ingestion_b", "LINESTRING", 32718, USER, PASSWORD, HOST, PORT, DATABASE_NAME, conn=conn)
        conn.close()
        print("✅ Test Case B passed.")
    except Exception as e:
        print(f"❌ Test Case B failed: {str(e)}")
        sys.exit(1)

    # 4. Test Case C: Using string 'None' as SRID (Robustness Test)
    try:
        print("\n--- Test Case C: String 'None' as SRID ---")
        df_to_postgres(gdf, "test_ingestion_c", "LINESTRING", "None", USER, PASSWORD, HOST, PORT, DATABASE_NAME)
        print("✅ Test Case C passed (Handled 'None' string).")
    except Exception as e:
        print(f"❌ Test Case C failed: {str(e)}")
        sys.exit(1)

    # 5. Test Case D: Using unparseable string for SRID
    try:
        print("\n--- Test Case D: Unparseable String as SRID ---")
        df_to_postgres(gdf, "test_ingestion_d", "LINESTRING", "INVALID", USER, PASSWORD, HOST, PORT, DATABASE_NAME)
        print("✅ Test Case D passed (Handled unparseable string).")
    except Exception as e:
        print(f"❌ Test Case D failed: {str(e)}")
        sys.exit(1)

    print("\n🎉 All Ingestion Tests Passed!")

if __name__ == "__main__":
    test_ingestion()
