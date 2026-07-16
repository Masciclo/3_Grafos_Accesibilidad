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

    net_table = "valdchil_rec_1784184395_internal_net"
    projects_table = "valdchil_rec_1784184395_projects"

    cur.execute(f"""
        SELECT 
            net.id,
            proj.parent_baseline_id,
            ST_Distance(net.geometry, proj.geometry) as dist,
            ST_Equals(net.geometry, proj.geometry) as is_equal,
            ST_Length(net.geometry) as net_len,
            ST_Length(proj.geometry) as proj_len
        FROM {net_table} net
        JOIN {projects_table} proj ON net.parent_baseline_id::integer = proj.parent_baseline_id::integer
        WHERE net.is_project = TRUE;
    """)
    rows = cur.fetchall()
    
    exact_match = 0
    close_match = 0
    far_match = 0
    total = len(rows)

    for r in rows:
        nid, pid, dist, is_equal, nlen, plen = r
        if is_equal or dist < 0.001:
            exact_match += 1
        elif dist < 1.0:
            close_match += 1
        else:
            far_match += 1

    print(f"Total project segments tagged: {total}")
    print(f"  Exact geometry matches (dist < 1mm): {exact_match}")
    print(f"  Close geometry matches (dist < 1m): {close_match}")
    print(f"  Far geometry matches (dist >= 1m): {far_match}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
