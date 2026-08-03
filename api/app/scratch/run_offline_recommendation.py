import os
import random
from core.recommendation import RecommendationEngine

def main():
    # Set seed for determinism
    random.seed(42)

    db_config = {
        'name': os.getenv("DATABASE_NAME", "ciclo_dev"),
        'user': os.getenv("DB_USER", "ciclo"),
        'password': os.getenv("DB_PASSWORD", "ciclo"),
        'host': os.getenv("HOST", "stationdb"),
        'port': 5432
    }
    data_base_path = "data"
    rec_engine = RecommendationEngine(db_config, data_base_path, "valdivia", 32718)
    
    seeds = [11520]
    reference_scenario = "current"
    budget = 2000.0
    sample_size = 1000
    lambdas = {
        'primary': 0.5, 'secondary': 0.5, 'tertiary': 0.5, 'residential': 0.5, 
        'trunk': 0.5, 'primary_link': 0.5, 'secondary_link': 0.5, 'tertiary_link': 0.5
    }
    
    print("--- RUNNING OFFLINE OPTIMIZATION ON UPDATED TOPOLOGY ---")
    selected = rec_engine._solve_greedy_growth(
        seed_edge_ids=seeds,
        reference_scenario=reference_scenario,
        budget=budget,
        sample_size=sample_size,
        highway_lambdas=lambdas
    )
    
    print(f"\nGreedy optimization selected {len(selected)} edges.")
    
    # Export GeoJSON
    proj_item = {
        "selected_edges": selected
    }
    
    geojson_path = rec_engine._export_geojson([proj_item], reference_scenario)
    print(f"Exported GeoJSON to: {geojson_path}")

if __name__ == "__main__":
    main()
