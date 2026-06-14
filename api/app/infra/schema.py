from infra.database import execute_query
from ui.components import diagnostic_handler

class SchemaGuard:
    """
    SchemaGuard: The deep module for ensuring database column parity and hygienic invariants.
    Consolidates 'ALTER TABLE' logic into a single point of truth.
    """
    
    # Standard internal network columns and their types
    NETWORK_COLUMNS = {
        "is_project": "BOOLEAN DEFAULT FALSE",
        "project_id": "TEXT",
        "parent_baseline_id": "TEXT",
        "impedance": "FLOAT DEFAULT 1.0",
        "od_flow": "NUMERIC DEFAULT 0",
        "highway": "TEXT",
        "length": "FLOAT",
        "cost": "FLOAT"
    }
    
    # Standard H3 grid columns
    H3_COLUMNS = {
        "pop_total": "FLOAT DEFAULT 0",
        "od_flow": "FLOAT DEFAULT 0",
        "m_osm": "FLOAT DEFAULT 0",
        "m_project": "FLOAT DEFAULT 0",
        "participating_in_analysis": "BOOLEAN DEFAULT TRUE"
    }

    @staticmethod
    def ensure_network_parity(conn, table_name):
        """
        Guarantees that the network table has all required columns for routing and delta analysis.
        """
        with conn.cursor() as cursor:
            for col, col_type in SchemaGuard.NETWORK_COLUMNS.items():
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {col} {col_type}")
        conn.commit()
        diagnostic_handler.report("SCHEMA_GUARD", "INFO", f"Network parity verified for {table_name}")

    @staticmethod
    def ensure_h3_parity(conn, table_name):
        """
        Guarantees that the H3 grid table has all required columns for analytical aggregation.
        """
        with conn.cursor() as cursor:
            for col, col_type in SchemaGuard.H3_COLUMNS.items():
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {col} {col_type}")
        conn.commit()
        diagnostic_handler.report("SCHEMA_GUARD", "INFO", f"H3 parity verified for {table_name}")
