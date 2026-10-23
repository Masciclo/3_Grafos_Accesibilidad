"""
regenerate_maps.py: Regenerates all MapLibre GL JS vector viewers for Santiago and Valdivia
conforming bijectively to the Plotly academic standard and driven by ciclo_map_reducer.js.
"""
import os
import sys

# Ensure api/app is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.maplibre_maps import MapLibreMapGenerator
from core.tile_sources import LiveMartinTileSource

def main():
    print("=== +Ciclo MapLibre Viewer Bijective Generator ===")
    tile_source = LiveMartinTileSource(host="http://localhost:3000")

    # 1. Santiago Maps
    santiago_dir = os.path.abspath("data/santiago/out/maps")
    os.makedirs(santiago_dir, exist_ok=True)
    generator_santiago = MapLibreMapGenerator(output_dir=santiago_dir, tile_source=tile_source)

    # Santiago Metropolitan core bounding box [min_lon, min_lat, max_lon, max_lat]
    santiago_bbox = [-70.82, -33.60, -70.48, -33.34]
    santiago_max_flow = 182345.0
    santiago_p50_flow = 696.0
    santiago_quantiles = [0.1, 696.0, 3193.0, 9625.0, 24046.0, 182345.0]

    print("\n--- Generating Santiago MapLibre Viewers ---")
    f1 = generator_santiago.generate_flow_map(
        scenario_prefix="santchil_baseline",
        bbox=santiago_bbox,
        max_flow=santiago_max_flow,
        p50_flow=santiago_p50_flow,
        city_key="santiago",
        quantiles=santiago_quantiles
    )
    print("Generated:", f1)

    # 1b. Santiago Bikelanes Flow Map (Always On, ADR-0003 network quantiles)
    f_bike_base = generator_santiago.generate_bikelanes_flow_map(
        scenario_prefix="santchil_baseline",
        bbox=santiago_bbox,
        max_flow=santiago_max_flow,
        p50_flow=santiago_p50_flow,
        city_key="santiago",
        quantiles=santiago_quantiles
    )
    print("Generated:", f_bike_base)

    f2 = generator_santiago.generate_impedance_map(
        scenario_prefix="santchil_baseline",
        city_key="santiago",
        bbox=santiago_bbox
    )
    print("Generated:", f2)

    f3 = generator_santiago.generate_flow_map(
        scenario_prefix="santchil_current",
        bbox=santiago_bbox,
        max_flow=santiago_max_flow,
        p50_flow=santiago_p50_flow,
        city_key="santiago",
        quantiles=santiago_quantiles
    )
    print("Generated:", f3)

    f_bike_curr = generator_santiago.generate_bikelanes_flow_map(
        scenario_prefix="santchil_current",
        bbox=santiago_bbox,
        max_flow=santiago_max_flow,
        p50_flow=santiago_p50_flow,
        city_key="santiago",
        quantiles=santiago_quantiles
    )
    print("Generated:", f_bike_curr)

    f4 = generator_santiago.generate_compare_map(
        scenario_prefix="santchil_current",
        reference_scenario_prefix="santchil_baseline",
        bbox=santiago_bbox,
        city_key="santiago",
        max_flow=santiago_max_flow,
        p50_flow=santiago_p50_flow,
        quantiles=santiago_quantiles
    )
    print("Generated:", f4)

    # Scenarios 1785478233 and 1785604682
    for rec_id in ["1785478233", "1785604682"]:
        scenario_name = f"santchil_rec_{rec_id}"
        f_delta = generator_santiago.generate_delta_map(
            scenario_prefix=scenario_name,
            bbox=santiago_bbox,
            max_delta=50000.0,
            city_key="santiago"
        )
        print("Generated:", f_delta)

        f_comp = generator_santiago.generate_compare_map(
            scenario_prefix=scenario_name,
            reference_scenario_prefix="santchil_baseline",
            bbox=santiago_bbox,
            city_key="santiago",
            max_flow=santiago_max_flow,
            p50_flow=santiago_p50_flow,
            quantiles=santiago_quantiles
        )
        print("Generated:", f_comp)

        f_perf = generator_santiago.generate_project_performance_map(
            scenario_prefix=scenario_name,
            bbox=santiago_bbox,
            max_flow=santiago_max_flow,
            p50_flow=santiago_p50_flow,
            city_key="santiago",
            quantiles=santiago_quantiles
        )
        print("Generated:", f_perf)

    # 1c. Santiago H3 Purpose Demand Maps
    santiago_purposes = {
        "work": 421.25,
        "study": 121.15,
        "shopping": 307.83,
        "personal": 73.96,
        "recreational": 163.65,
        "returning_home": 138.58
    }
    for purp, p95_val in santiago_purposes.items():
        f_h3 = generator_santiago.generate_h3_purpose_map(
            scenario_prefix="santchil_baseline",
            bbox=santiago_bbox,
            purpose=purp,
            p95=p95_val,
            city_key="santiago"
        )
        print("Generated:", f_h3)

    # 2. Valdivia Maps
    valdivia_dir = os.path.abspath("data/valdivia/out/maps")
    os.makedirs(valdivia_dir, exist_ok=True)
    generator_valdivia = MapLibreMapGenerator(output_dir=valdivia_dir, tile_source=tile_source)

    valdivia_bbox = [-73.28, -39.87, -73.18, -39.78]
    valdivia_max_flow = 66552.0
    valdivia_p50_flow = 448.0
    valdivia_quantiles = [0.2, 448.0, 2912.0, 13545.0, 31847.0, 66552.0]

    print("\n--- Generating Valdivia MapLibre Viewers ---")
    v1 = generator_valdivia.generate_flow_map(
        scenario_prefix="valdchil_baseline",
        bbox=valdivia_bbox,
        max_flow=valdivia_max_flow,
        p50_flow=valdivia_p50_flow,
        city_key="valdivia",
        quantiles=valdivia_quantiles
    )
    print("Generated:", v1)

    v_bike_base = generator_valdivia.generate_bikelanes_flow_map(
        scenario_prefix="valdchil_baseline",
        bbox=valdivia_bbox,
        max_flow=valdivia_max_flow,
        p50_flow=valdivia_p50_flow,
        city_key="valdivia",
        quantiles=valdivia_quantiles
    )
    print("Generated:", v_bike_base)

    v2 = generator_valdivia.generate_impedance_map(
        scenario_prefix="valdchil_baseline",
        city_key="valdivia",
        bbox=valdivia_bbox
    )
    print("Generated:", v2)

    v3 = generator_valdivia.generate_flow_map(
        scenario_prefix="valdchil_current",
        bbox=valdivia_bbox,
        max_flow=valdivia_max_flow,
        p50_flow=valdivia_p50_flow,
        city_key="valdivia",
        quantiles=valdivia_quantiles
    )
    print("Generated:", v3)

    v_bike_curr = generator_valdivia.generate_bikelanes_flow_map(
        scenario_prefix="valdchil_current",
        bbox=valdivia_bbox,
        max_flow=valdivia_max_flow,
        p50_flow=valdivia_p50_flow,
        city_key="valdivia",
        quantiles=valdivia_quantiles
    )
    print("Generated:", v_bike_curr)

    v4 = generator_valdivia.generate_compare_map(
        scenario_prefix="valdchil_current",
        reference_scenario_prefix="valdchil_baseline",
        bbox=valdivia_bbox,
        city_key="valdivia",
        max_flow=valdivia_max_flow,
        p50_flow=valdivia_p50_flow,
        quantiles=valdivia_quantiles
    )
    print("Generated:", v4)

    v5 = generator_valdivia.generate_delta_map(
        scenario_prefix="valdchil_current",
        bbox=valdivia_bbox,
        max_delta=5000.0,
        city_key="valdivia"
    )
    print("Generated:", v5)

    # Valdivia Project Performance Map
    v_perf = generator_valdivia.generate_project_performance_map(
        scenario_prefix="valdchil_project_v1",
        bbox=valdivia_bbox,
        max_flow=valdivia_max_flow,
        p50_flow=valdivia_p50_flow,
        city_key="valdivia",
        quantiles=valdivia_quantiles
    )
    print("Generated:", v_perf)

    # Valdivia H3 Purpose Demand Maps
    valdivia_purposes = {
        "work": 321.13,
        "study": 97.56,
        "shopping": 445.62,
        "personal": 133.36,
        "recreational": 98.50,
        "returning_home": 1365.80
    }
    for purp, p95_val in valdivia_purposes.items():
        v_h3 = generator_valdivia.generate_h3_purpose_map(
            scenario_prefix="valdchil_baseline",
            bbox=valdivia_bbox,
            purpose=purp,
            p95=p95_val,
            city_key="valdivia"
        )
        print("Generated:", v_h3)

    # Sync generated viewers to both data directories
    import shutil
    for city in ["santiago", "valdivia"]:
        src_dir = os.path.abspath(f"data/{city}/out/maps")
        dst_dir = os.path.abspath(f"grafos-accesibilidad/data/{city}/out/maps")
        if os.path.exists(src_dir) and os.path.exists(os.path.dirname(dst_dir)):
            os.makedirs(dst_dir, exist_ok=True)
            for f in os.listdir(src_dir):
                if f.endswith(".html"):
                    shutil.copy2(os.path.join(src_dir, f), os.path.join(dst_dir, f))

    print("\n✔ All MapLibre vector maps regenerated and synced successfully!")

if __name__ == "__main__":
    main()
