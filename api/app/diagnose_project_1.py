import os
import pandas as pd
from sqlalchemy import create_engine

def check_project_connectivity(scenario_prefix):
    user, password, host, port, db = os.environ.get('DB_USER'), os.environ.get('DB_PASSWORD'), os.environ.get('HOST'), os.environ.get('PORT'), os.environ.get('DATABASE_NAME')
    engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{db}')
    
    print(f"\n--- [DIAGNOSE] Checking Project 1 Connectivity for {scenario_prefix} ---")
    
    # 1. Existence check
    query_existence = f"SELECT count(*) as count FROM {scenario_prefix}_internal_net WHERE project_id = '1';"
    count = pd.read_sql(query_existence, engine).iloc[0]['count']
    print(f"Segments for Project 1: {count}")
    
    if count == 0:
        print("FAIL: Project 1 does not exist in the internal network.")
        return False

    # 2. Node Degree check
    query_degree = f"""
    WITH p_nodes AS (
        SELECT source as node_id FROM {scenario_prefix}_internal_net WHERE project_id = '1'
        UNION
        SELECT target FROM {scenario_prefix}_internal_net WHERE project_id = '1'
    )
    SELECT 
        n.node_id,
        count(e.id) as degree,
        string_agg(DISTINCT CASE WHEN e.is_project THEN 'PROJECT' ELSE 'BASE' END, ', ') as types
    FROM p_nodes n
    JOIN {scenario_prefix}_internal_net e ON n.node_id = e.source OR n.node_id = e.target
    GROUP BY n.node_id;
    """
    df_degree = pd.read_sql(query_degree, engine)
    print("\nNode Degrees:")
    print(df_degree)
    
    # Check if any endpoint has degree 1
    islands = df_degree[df_degree['degree'] == 1]
    if not islands.empty:
        print(f"\nFAIL: Project 1 has {len(islands)} isolated endpoints (degree 1).")
        return False

    # 3. Flow check
    query_flow = f"SELECT sum(od_flow) as total_flow FROM {scenario_prefix}_network WHERE project_id = '1';"
    total_flow = pd.read_sql(query_flow, engine).iloc[0]['total_flow']
    print(f"\nTotal Flow on Project 1: {total_flow}")
    
    if total_flow == 0:
        print("FAIL: Project 1 has connectivity but NO flow. (Impedance or Routing issue)")
        return False
    
    print("PASS: Project 1 is connected and has load.")
    return True

if __name__ == "__main__":
    import sys
    prefix = sys.argv[1] if len(sys.argv) > 1 else "valdchil_v18_restored"
    check_project_connectivity(prefix)
