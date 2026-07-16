import os
import psycopg2

def main():
    conn = psycopg2.connect(
        dbname=os.getenv("DATABASE_NAME", "ciclo_dev"),
        user=os.getenv("DB_USER", "ciclo"),
        password=os.getenv("DB_PASSWORD", "ciclo"),
        host=os.getenv("HOST", "stationdb"),
        port=5432
    )
    cur = conn.cursor()

    print("--- SEARCHING FOR TOPOLOGICAL BREAKS (TOUCHING BUT NOT CONNECTED) ---")

    # Find edges that are within 1cm of each other but do not share a node
    cur.execute("""
        SELECT 
            a.id as edge_a,
            b.id as edge_b,
            a.original_highway as highway_a,
            b.original_highway as highway_b,
            ST_Distance(a.geometry, b.geometry) as dist,
            ST_AsText(ST_Intersection(a.geometry, b.geometry)) as intersection_wkt,
            ST_AsText(a.geometry) as wkt_a,
            ST_AsText(b.geometry) as wkt_b
        FROM valdchil_current_internal_net a
        JOIN valdchil_current_internal_net b ON a.id < b.id AND ST_DWithin(a.geometry, b.geometry, 0.01)
        WHERE NOT (a.source = b.source OR a.source = b.target OR a.target = b.source OR a.target = b.target)
          -- Exclude cycleway-to-cycleway and cycleway-to-street crossings if they are parallel offset
          AND NOT (
              (a.original_highway = 'cycleway' AND b.original_highway != 'cycleway')
              OR (b.original_highway = 'cycleway' AND a.original_highway != 'cycleway')
          )
        LIMIT 15;
    """)
    rows = cur.fetchall()
    print(f"Found {len(rows)} topological breaks between street segments:")
    for idx, row in enumerate(rows):
        print(f"\nBreak {idx+1}:")
        print(f"  Edge A: {row[0]} ({row[2]})")
        print(f"  Edge B: {row[1]} ({row[3]})")
        print(f"  Distance: {row[4]} meters")
        print(f"  Intersection WKT: {row[5]}")
        print(f"  WKT A: {row[6][:120]}...")
        print(f"  WKT B: {row[7][:120]}...")

    # Let's count the total number of breaks for streets only
    cur.execute("""
        SELECT COUNT(*)
        FROM valdchil_current_internal_net a
        JOIN valdchil_current_internal_net b ON a.id < b.id AND ST_DWithin(a.geometry, b.geometry, 0.01)
        WHERE NOT (a.source = b.source OR a.source = b.target OR a.target = b.source OR a.target = b.target)
          AND a.original_highway != 'cycleway' AND b.original_highway != 'cycleway';
    """)
    total_breaks = cur.fetchone()[0]
    print(f"\nTotal topological breaks between street-street segments: {total_breaks}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
