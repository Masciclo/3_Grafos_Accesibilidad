import os
import tempfile
import pytest
from core.maplibre_maps import MapLibreMapGenerator
from core.tile_sources import LiveMartinTileSource, PMTilesArchiveTileSource

def test_maplibre_generator_flow_html():
    with tempfile.TemporaryDirectory() as tmpdir:
        generator = MapLibreMapGenerator(output_dir=tmpdir)
        bbox = [-73.25, -39.85, -73.15, -39.75]
        output_file = generator.generate_flow_map(
            scenario_prefix="valdivia_baseline",
            bbox=bbox,
            total_trips=25000.0,
            max_flow=850.0,
            p50_flow=45.0
        )

        assert os.path.exists(output_file)
        assert output_file.endswith("valdivia_baseline_flow.html")

        # Verify file size is featherweight (< 40 KB)
        size_bytes = os.path.getsize(output_file)
        assert size_bytes < 40000

        with open(output_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "maplibregl.Map" in content
        assert "http://localhost:3000/mvt_network/{z}/{x}/{y}?scenario=valdivia_baseline" in content
        assert "valdivia_baseline" in content
        assert "<b>Legend</b>" in content
        assert "Existing Cycleway" in content
        assert "map-header" not in content

def test_maplibre_generator_pmtiles_protocol():
    with tempfile.TemporaryDirectory() as tmpdir:
        source = PMTilesArchiveTileSource(output_dir=tmpdir)
        generator = MapLibreMapGenerator(output_dir=tmpdir, tile_source=source)
        bbox = [-70.75, -33.55, -70.55, -33.35]
        output_file = generator.generate_flow_map(
            scenario_prefix="santiago_v1",
            bbox=bbox,
            total_trips=120000.0,
            max_flow=4500.0,
            p50_flow=250.0
        )

        with open(output_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "pmtiles.Protocol" in content
        assert "pmtiles://./santiago_v1.pmtiles" in content

def test_maplibre_generator_delta_html():
    with tempfile.TemporaryDirectory() as tmpdir:
        generator = MapLibreMapGenerator(output_dir=tmpdir)
        bbox = [-73.25, -39.85, -73.15, -39.75]
        output_file = generator.generate_delta_map(
            scenario_prefix="valdivia_project_v1",
            bbox=bbox,
            max_delta=320.0
        )

        assert os.path.exists(output_file)
        assert output_file.endswith("valdivia_project_v1_delta.html")
        assert os.path.getsize(output_file) < 40000

        with open(output_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "http://localhost:3000/mvt_delta/{z}/{x}/{y}?scenario=valdivia_project_v1" in content
        assert "delta_flow" in content
        assert "#b2182b" in content
        assert "#2166ac" in content
        assert "<b>Legend</b>" in content
        assert "Critical Peak Increase" in content
        assert "map-header" not in content

def test_maplibre_generator_compare_html():
    with tempfile.TemporaryDirectory() as tmpdir:
        generator = MapLibreMapGenerator(output_dir=tmpdir)
        bbox = [-73.25, -39.85, -73.15, -39.75]
        output_file = generator.generate_compare_map(
            scenario_prefix="valdivia_project_v1",
            reference_scenario_prefix="valdivia_baseline",
            bbox=bbox
        )

        assert os.path.exists(output_file)
        assert output_file.endswith("valdivia_project_v1_compare.html")
        assert os.path.getsize(output_file) < 40000

        with open(output_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "before-map" in content
        assert "after-map" in content
        assert "slider-container" in content
        assert "valdivia_baseline" in content
        assert "valdivia_project_v1" in content

def test_maplibre_generator_impedance_html():
    with tempfile.TemporaryDirectory() as tmpdir:
        generator = MapLibreMapGenerator(output_dir=tmpdir)
        bbox = [-73.25, -39.85, -73.15, -39.75]
        custom_weights = {
            "primary": 20.0,
            "secondary": 8.0,
            "tertiary": 4.0,
            "local": 2.0,
            "bike": 0.3
        }
        output_file = generator.generate_impedance_map(
            scenario_prefix="valdivia_project_v1",
            city_key="valdivia",
            bbox=bbox,
            imp_weights=custom_weights
        )

        assert os.path.exists(output_file)
        assert output_file.endswith("valdivia_project_v1_impedance.html")
        assert os.path.getsize(output_file) < 40000

        with open(output_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "<b>Legend</b>" in content
        assert "context-water" in content
        assert "context-forests" in content
        assert "context-urban-limit" in content
        assert "road-hierarchy" in content
        assert "Residential Street" in content
        assert "Primary Road" in content
        assert "#27ae60" in content
        assert "map-header" not in content

def test_maplibre_generator_context_layers_in_flow_and_delta():
    with tempfile.TemporaryDirectory() as tmpdir:
        generator = MapLibreMapGenerator(output_dir=tmpdir)
        bbox = [-73.25, -39.85, -73.15, -39.75]

        flow_file = generator.generate_flow_map(
            scenario_prefix="valdivia_baseline",
            bbox=bbox,
            city_key="valdivia"
        )
        with open(flow_file, "r", encoding="utf-8") as f:
            flow_content = f.read()
        assert "context_source" in flow_content
        assert "context-water" in flow_content
        assert "context-buildings" in flow_content
        assert "context-forests" in flow_content
        assert "context-urban-limit" in flow_content

        delta_file = generator.generate_delta_map(
            scenario_prefix="valdivia_project_v1",
            bbox=bbox,
            city_key="valdivia"
        )
        with open(delta_file, "r", encoding="utf-8") as f:
            delta_content = f.read()
        assert "context_source" in delta_content
        assert "context-water" in delta_content
        assert "context-buildings" in delta_content

def test_maplibre_generator_all_pmtiles_support():
    with tempfile.TemporaryDirectory() as tmpdir:
        source = PMTilesArchiveTileSource(output_dir=tmpdir)
        generator = MapLibreMapGenerator(output_dir=tmpdir, tile_source=source)
        bbox = [-73.25, -39.85, -73.15, -39.75]

        compare_file = generator.generate_compare_map(
            scenario_prefix="valdivia_project_v1",
            reference_scenario_prefix="valdivia_baseline",
            bbox=bbox,
            city_key="valdivia"
        )
        with open(compare_file, "r", encoding="utf-8") as f:
            compare_content = f.read()
        assert "pmtiles.Protocol" in compare_content
        assert "pmtiles://" in compare_content

        imp_file = generator.generate_impedance_map(
            scenario_prefix="valdivia_project_v1",
            city_key="valdivia",
            bbox=bbox
        )
        with open(imp_file, "r", encoding="utf-8") as f:
            imp_content = f.read()
        assert "pmtiles.Protocol" in imp_content
        assert "pmtiles://" in imp_content

def test_maplibre_generator_bikelanes_and_performance_html():
    with tempfile.TemporaryDirectory() as tmpdir:
        generator = MapLibreMapGenerator(output_dir=tmpdir)
        bbox = [-70.82, -33.60, -70.48, -33.34]

        # 1. Bikelanes flow map
        bike_file = generator.generate_bikelanes_flow_map(
            scenario_prefix="santchil_baseline",
            bbox=bbox,
            total_trips=150000.0,
            max_flow=180000.0,
            p50_flow=700.0,
            city_key="santiago"
        )
        assert os.path.exists(bike_file)
        assert bike_file.endswith("santchil_baseline_bikelanes_flow.html")
        assert os.path.getsize(bike_file) < 40000

        with open(bike_file, "r", encoding="utf-8") as f:
            bike_content = f.read()
        assert "network-bikelanes" in bike_content
        assert "#c8e6c9" in bike_content
        assert "#1b5e20" in bike_content

        # 2. Project Performance map
        perf_file = generator.generate_project_performance_map(
            scenario_prefix="santchil_rec_1785604682",
            bbox=bbox,
            total_trips=150000.0,
            max_flow=180000.0,
            p50_flow=700.0,
            city_key="santiago"
        )
        assert os.path.exists(perf_file)
        assert perf_file.endswith("santchil_rec_1785604682_performance.html")
        assert os.path.getsize(perf_file) < 40000

        with open(perf_file, "r", encoding="utf-8") as f:
            perf_content = f.read()
        assert "network-performance" in perf_content
        assert "Strategic Artery" in perf_content
        assert "#4fa8e3" in perf_content  # Existing cycleway light blue

def test_maplibre_generator_h3_purpose_html():
    with tempfile.TemporaryDirectory() as tmpdir:
        generator = MapLibreMapGenerator(output_dir=tmpdir)
        bbox = [-70.82, -33.60, -70.48, -33.34]

        h3_file = generator.generate_h3_purpose_map(
            scenario_prefix="santchil_baseline",
            bbox=bbox,
            purpose="work",
            p95=2500.0,
            city_key="santiago"
        )
        assert os.path.exists(h3_file)
        assert h3_file.endswith("santchil_baseline_work_map.html")
        assert os.path.getsize(h3_file) < 40000

        with open(h3_file, "r", encoding="utf-8") as f:
            h3_content = f.read()
        assert "h3-hexagons" in h3_content
        assert "trips_work" in h3_content
        assert "purpose-select" in h3_content
        assert "mvt_h3" in h3_content

def test_maplibre_generator_progressive_lod(tmp_path):
    generator = MapLibreMapGenerator(output_dir=str(tmp_path))
    bbox = [-70.7, -33.5, -70.6, -33.4]
    html_path = generator.generate_flow_map(
        scenario_prefix="santchil_baseline",
        bbox=bbox,
        total_trips=100.0,
        max_flow=500.0,
        p50_flow=50.0,
        city_key="santiago"
    )
    assert os.path.exists(html_path)
    with open(html_path, "r", encoding="utf-8") as f:
        flow_content = f.read()

    # Verify public viewer contains zoom LoD progressive transitions:
    # 1. Opacity stops for background streets: 12 -> 0.0, 13 -> 0.15, 15 -> 0.40
    assert "12, 0.0" in flow_content
    assert "13, 0.15" in flow_content
    assert "15, 0.4" in flow_content
    # 2. Width stops for background streets: 12 -> 0.0, 13 -> 0.3, 15 -> 0.8
    assert "13, [\"case\"" in flow_content or "13, ['case'" in flow_content
    assert "15, [\"case\"" in flow_content or "15, ['case'" in flow_content

    # Also test delta map public generation
    delta_path = generator.generate_delta_map(
        scenario_prefix="santchil_baseline",
        bbox=bbox,
        max_delta=250.0,
        city_key="santiago"
    )
    assert os.path.exists(delta_path)
    with open(delta_path, "r", encoding="utf-8") as f:
        delta_content = f.read()

    assert "13, 0.15" in delta_content or "13,0.15" in delta_content
    assert "15, 0.4" in delta_content or "15,0.4" in delta_content
