import os
import psycopg2

def test_plugging_degree1(cur, dist_limit):
    cur.execute("ROLLBACK;")
    cur.execute("BEGIN;")

    # 1. Identify cycleway nodes and their degrees in the cycleway-only network
    cur.execute("""
        DROP TABLE IF EXISTS temp_cycleway_node_degrees;
        CREATE TEMP TABLE temp_cycleway_node_degrees AS
        SELECT node_id, COUNT(*) as degree
        FROM (
            SELECT source as node_id FROM valdchil_current_internal_net WHERE original_highway = 'cycleway'
            UNION ALL
            SELECT target as node_id FROM valdchil_current_internal_net WHERE original_highway = 'cycleway'
        ) sub
        GROUP BY node_id;
    """)

    # 2. Identify isolated cycleway endpoints (degree = 1 and not connected to any street)
    cur.execute("""
        DROP TABLE IF EXISTS temp_isolated_cycleway_nodes;
        CREATE TEMP TABLE temp_isolated_cycleway_nodes AS
        SELECT 
            d.node_id,
            v.the_geom
        FROM temp_cycleway_node_degrees d
        JOIN valdchil_current_internal_net_vertices_pgr v ON d.node_id = v.id
        WHERE d.degree = 1 -- Only snap dead-ends!
          AND NOT EXISTS (
              SELECT 1 FROM valdchil_current_internal_net e 
              WHERE (e.source = d.node_id OR e.target = d.node_id) 
                AND e.original_highway != 'cycleway'
          );
    """)

    cur.execute("SELECT COUNT(*) FROM temp_isolated_cycleway_nodes;")
    isolated_cnt = cur.fetchone()[0]

    # 3. Map isolated cycleway endpoints to the nearest street node
    cur.execute(f"""
        DROP TABLE IF EXISTS temp_cycleway_plugging_map;
        CREATE TEMP TABLE temp_cycleway_plugging_map AS
        SELECT DISTINCT ON (i.node_id)
            i.node_id as isolated_node_id,
            target.id as target_node_id
        FROM temp_isolated_cycleway_nodes i
        CROSS JOIN LATERAL (
            SELECT v.id 
            FROM valdchil_current_internal_net_vertices_pgr v
            WHERE v.id NOT IN (SELECT node_id FROM temp_isolated_cycleway_nodes)
              AND ST_DWithin(i.the_geom, v.the_geom, {dist_limit})
              AND EXISTS (SELECT 1 FROM valdchil_current_internal_net e WHERE (e.source = v.id OR e.target = v.id) AND e.original_highway != 'cycleway')
            ORDER BY i.the_geom <-> v.the_geom
            LIMIT 1
        ) target;
    """)

    cur.execute("SELECT COUNT(*) FROM temp_cycleway_plugging_map;")
    mapped_cnt = cur.fetchone()[0]

    # 4. Update the network table
    cur.execute("""
        UPDATE valdchil_current_internal_net SET source = m.target_node_id 
        FROM temp_cycleway_plugging_map m 
        WHERE source = m.isolated_node_id AND original_highway = 'cycleway';

        UPDATE valdchil_current_internal_net SET target = m.target_node_id 
        FROM temp_cycleway_plugging_map m 
        WHERE target = m.isolated_node_id AND original_highway = 'cycleway';
    """)

    # Check if we created any self-loops (source = target)
    cur.execute("""
        SELECT COUNT(*) 
        FROM valdchil_current_internal_net 
        WHERE original_highway = 'cycleway' AND source = target;
    """)
    loops = cur.fetchone()[0]

    # Recalculate components
    cur.execute("""
        DROP TABLE IF EXISTS temp_components CASCADE;
        CREATE TEMP TABLE temp_components AS
        SELECT * FROM pgr_connectedComponents(
            'SELECT id, source::integer, target::integer, cost FROM valdchil_current_internal_net'
        );

        DROP TABLE IF EXISTS temp_net_components CASCADE;
        CREATE TEMP TABLE temp_net_components AS
        SELECT 
            n.*,
            c.component
        FROM valdchil_current_internal_net n
        JOIN valdchil_current_internal_net_vertices_pgr v ON n.source = v.id
        JOIN temp_components c ON v.id = c.node;
    """)

    # Count LCC cycleways
    cur.execute("""
        WITH lcc AS (
            SELECT component
            FROM temp_net_components
            GROUP BY component
            ORDER BY COUNT(*) DESC
            LIMIT 1
        )
        SELECT COUNT(*), SUM(ST_Length(geometry))
        FROM temp_net_components n
        JOIN lcc ON n.component = lcc.component
        WHERE n.original_highway = 'cycleway';
    """)
    after_cnt, after_len = cur.fetchone()
    print(f"Dist={dist_limit}m: Isolated endpoints={isolated_cnt}, Snapped={mapped_cnt} -> Cycleways in LCC: count={after_cnt} ({after_cnt/610*100:.1f}%), length={after_len or 0:.1f}m, Self-loops: {loops}")
    cur.execute("ROLLBACK;")

def main():
    conn = psycopg2.connect(
        dbname=os.getenv("DATABASE_NAME", "ciclo_dev"),
        user=os.getenv("DB_USER", "ciclo"),
        password=os.getenv("DB_PASSWORD", "ciclo"),
        host=os.getenv("HOST", "stationdb"),
        port=5432
    )
    cur = conn.cursor()

    print("--- TESTING ENDPOINT-ONLY CYCLEWAY SNAPPING ---")
    for dist in [5.0, 10.0, 15.0, 20.0, 30.0, 50.0]:
        test_plugging_dist_original(cur, dist)
        test_plugging_degree1(cur, dist)
        print("-" * 50)

    cur.close()
    conn.close()

def test_plugging_dist_original(cur, dist_limit):
    cur.execute("ROLLBACK;")
    cur.execute("BEGIN;")
    cur.execute(f"""
        DROP TABLE IF EXISTS temp_cycleway_nodes;
        CREATE TEMP TABLE temp_cycleway_nodes AS
        SELECT DISTINCT node_id FROM (
            SELECT source as node_id FROM valdchil_current_internal_net WHERE original_highway = 'cycleway'
            UNION
            SELECT target FROM valdchil_current_internal_net WHERE original_highway = 'cycleway'
        ) sub;

        DROP TABLE IF EXISTS temp_isolated_cycleway_nodes;
        CREATE TEMP TABLE temp_isolated_cycleway_nodes AS
        SELECT 
            cn.node_id,
            v.the_geom
        FROM temp_cycleway_nodes cn
        JOIN valdchil_current_internal_net_vertices_pgr v ON cn.node_id = v.id
        WHERE NOT EXISTS (
            SELECT 1 FROM valdchil_current_internal_net e 
            WHERE (e.source = cn.node_id OR e.target = cn.node_id) 
              AND e.original_highway != 'cycleway'
        );

        DROP TABLE IF EXISTS temp_cycleway_plugging_map;
        CREATE TEMP TABLE temp_cycleway_plugging_map AS
        SELECT DISTINCT ON (i.node_id)
            i.node_id as isolated_node_id,
            target.id as target_node_id
        FROM temp_isolated_cycleway_nodes i
        CROSS JOIN LATERAL (
            SELECT v.id 
            FROM valdchil_current_internal_net_vertices_pgr v
            WHERE v.id NOT IN (SELECT node_id FROM temp_isolated_cycleway_nodes)
              AND ST_DWithin(i.the_geom, v.the_geom, {dist_limit})
              AND EXISTS (SELECT 1 FROM valdchil_current_internal_net e WHERE (e.source = v.id OR e.target = v.id) AND e.original_highway != 'cycleway')
            ORDER BY i.the_geom <-> v.the_geom
            LIMIT 1
        ) target;

        UPDATE valdchil_current_internal_net SET source = m.target_node_id 
        FROM temp_cycleway_plugging_map m 
        WHERE source = m.isolated_node_id AND original_highway = 'cycleway';

        UPDATE valdchil_current_internal_net SET target = m.target_node_id 
        FROM temp_cycleway_plugging_map m 
        WHERE target = m.isolated_node_id AND original_highway = 'cycleway';
    """)
    cur.execute("SELECT COUNT(*) FROM valdchil_current_internal_net WHERE original_highway = 'cycleway' AND source = target;")
    loops = cur.fetchone()[0]
    print(f"Dist={dist_limit}m (ORIGINAL): Self-loops: {loops}")
    cur.execute("ROLLBACK;")

if __name__ == "__main__":
    main()
