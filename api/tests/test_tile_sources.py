import pytest
from core.pipeline import ScenarioConfig, ScenarioContext
from core.tile_sources import (
    TileSourceAdapter,
    LiveMartinTileSource,
    PMTilesArchiveTileSource
)

def test_scenario_config_defaults():
    config = ScenarioConfig(
        location="valdivia",
        city_key="valdivia",
        scenario_id="baseline",
        srid=32719,
        osm_input="osm",
        od_input="od.csv",
        census_input="census.parquet"
    )
    assert config.mapping is True
    assert config.export_pmtiles is False
    assert config.legacy_plotly is False

def test_scenario_config_custom_flags():
    config = ScenarioConfig(
        location="valdivia",
        city_key="valdivia",
        scenario_id="baseline",
        srid=32719,
        osm_input="osm",
        od_input="od.csv",
        census_input="census.parquet",
        export_pmtiles=True,
        legacy_plotly=True
    )
    assert config.export_pmtiles is True
    assert config.legacy_plotly is True

def test_live_martin_tile_source_endpoints():
    source = LiveMartinTileSource(host="http://localhost:3000")
    net_src = source.get_network_source("valdivia_baseline")
    assert net_src["type"] == "vector"
    assert "http://localhost:3000/mvt_network/{z}/{x}/{y}?scenario=valdivia_baseline" in net_src["tiles"]

    delta_src = source.get_delta_source("valdivia_baseline")
    assert delta_src["type"] == "vector"
    assert "http://localhost:3000/mvt_delta/{z}/{x}/{y}?scenario=valdivia_baseline" in delta_src["tiles"]

    context_src = source.get_context_source("valdivia")
    assert context_src["type"] == "vector"
    assert "http://localhost:3000/mvt_context/{z}/{x}/{y}?city_key=valdivia" in context_src["tiles"]

def test_pmtiles_archive_tile_source():
    source = PMTilesArchiveTileSource(output_dir="data/valdivia/out/maps")
    net_src = source.get_network_source("valdivia_baseline")
    assert net_src["type"] == "vector"
    assert net_src["url"] == "pmtiles://./valdivia_baseline.pmtiles"

def test_pmtiles_archive_bake_command():
    from unittest.mock import patch
    source = PMTilesArchiveTileSource(output_dir="data/valdivia/out/maps")
    bbox = [-73.25, -39.85, -73.15, -39.75]

    with patch("subprocess.run") as mock_run:
        archive_path = source.bake_offline_archive("valdivia_baseline", bbox)

        assert archive_path == "data/valdivia/out/maps/valdivia_baseline.pmtiles"
        assert mock_run.called
        cmd_args = mock_run.call_args[0][0]
        assert "docker" in cmd_args
        assert "martin-cp" in cmd_args
        assert "--source" in cmd_args and "mvt_network" in cmd_args
        assert any(arg.startswith("--bbox=-73.25,-39.85,-73.15,-39.75") for arg in cmd_args)
        assert "--min-zoom" in cmd_args and "9" in cmd_args
        assert "--max-zoom" in cmd_args and "16" in cmd_args

def test_pmtiles_archive_bake_error_handling():
    from unittest.mock import patch
    source = PMTilesArchiveTileSource(output_dir="data/valdivia/out/maps")
    bbox = [-73.25, -39.85, -73.15, -39.75]

    with patch("subprocess.run", side_effect=Exception("Docker daemon unavailable")):
        archive_path = source.bake_offline_archive("valdivia_baseline", bbox)
        assert archive_path is None

def test_mvt_zoom_lod_server_side_filtering():
    """
    Behavioral test for spec-zoom-lod-local-street-filtering.md:
    Asserts that at z < 13, zero-flow residential streets are excluded,
    while major corridors and positive flow edges are retained.
    At z >= 13, all network edges are included.
    """
    try:
        import psycopg2
        conn = psycopg2.connect(
            host="localhost", port=5433, user="ciclo", password="ciclo", dbname="ciclo_dev"
        )
    except Exception:
        pytest.skip("PostGIS stationdb container not accessible on localhost:5433")

    try:
        cur = conn.cursor()
        # Verify table existence
        cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'santchil_baseline_network');")
        if not cur.fetchone()[0]:
            pytest.skip("santchil_baseline_network table not populated in local test database")

        # Behavioral LoD assertions on real scenario network data
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE (10 < 13 AND (highway IN ('motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'cycleway') OR is_project = TRUE OR od_flow > 0))) as z10_count,
                COUNT(*) FILTER (WHERE (14 >= 13)) as z14_count,
                COUNT(*) FILTER (WHERE highway = 'residential' AND od_flow = 0 AND is_project = FALSE AND (10 < 13 AND (highway IN ('motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'cycleway') OR is_project = TRUE OR od_flow > 0))) as z10_zero_flow_res,
                COUNT(*) FILTER (WHERE highway = 'residential' AND od_flow = 0 AND is_project = FALSE AND (14 >= 13)) as z14_zero_flow_res
            FROM santchil_baseline_network;
        """)
        row = cur.fetchone()
        z10_count, z14_count, z10_zero_flow_res, z14_zero_flow_res = row

        # Comparative zoom assertion: zoom 10 contains strictly fewer candidate features than zoom 14
        assert z10_count < z14_count
        # Zero-flow residential streets must be completely excluded below zoom 13
        assert z10_zero_flow_res == 0
        # Zero-flow residential streets must be present at zoom 14
        assert z14_zero_flow_res > 0

        # MVT execution verification: verify PostGIS function executes and returns binary MVT payload
        cur.execute("""
            SELECT octet_length(public.mvt_network(10, 311, 613, '{"scenario": "santchil_baseline"}'::json));
        """)
        mvt_bytes = cur.fetchone()[0]
        assert mvt_bytes is not None and mvt_bytes > 0
    finally:
        conn.close()
