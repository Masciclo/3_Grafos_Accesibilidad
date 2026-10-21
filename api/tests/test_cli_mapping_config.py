import pytest
import argparse
from ui.dashboard import PipelineUI

def test_pipeline_ui_mapping_engine_display_default():
    parser = argparse.ArgumentParser()
    parser.add_argument("--location", default="valdivia")
    parser.add_argument("--scenario_id", default="baseline")
    parser.add_argument("--mapping", action="store_true", default=True)
    parser.add_argument("--export-pmtiles", dest="export_pmtiles", action="store_true", default=False)
    parser.add_argument("--legacy-plotly", "--legacy-visualization", "--legacy-viz", dest="legacy_plotly", action="store_true", default=False)
    args = parser.parse_args([])

    ui = PipelineUI("valdivia", 32719, args=args)
    # Verify Stage 9 dynamic label
    phase_9 = next((p for p in ui.phases if p["id"] == 9), None)
    assert phase_9 is not None
    assert phase_9["name"] == "Academic Mapping (MapLibre Vector Tiles)"

    # Verify make_config_table contains MapLibre and Martin
    table = ui.make_config_table()
    rows = [r for r in table.columns[0]._cells]
    vals = [str(r) for r in table.columns[1]._cells]
    assert "Mapping Engine" in rows
    idx = rows.index("Mapping Engine")
    assert "MapLibre GL JS" in vals[idx]
    assert "Martin Vector Tiles" in vals[idx]

def test_pipeline_ui_mapping_engine_display_legacy_visualization():
    parser = argparse.ArgumentParser()
    parser.add_argument("--location", default="valdivia")
    parser.add_argument("--scenario_id", default="baseline")
    parser.add_argument("--mapping", action="store_true", default=True)
    parser.add_argument("--export-pmtiles", dest="export_pmtiles", action="store_true", default=False)
    parser.add_argument("--legacy-plotly", "--legacy-visualization", "--legacy-viz", dest="legacy_plotly", action="store_true", default=False)
    args = parser.parse_args(["--legacy-visualization"])

    assert args.legacy_plotly is True
    ui = PipelineUI("valdivia", 32719, args=args)
    phase_9 = next((p for p in ui.phases if p["id"] == 9), None)
    assert phase_9 is not None
    assert phase_9["name"] == "Academic Mapping (Legacy Plotly)"

    table = ui.make_config_table()
    rows = [r for r in table.columns[0]._cells]
    vals = [str(r) for r in table.columns[1]._cells]
    idx = rows.index("Mapping Engine")
    assert "Legacy Plotly" in vals[idx]

def test_screen_2_audit_layout_includes_config_table():
    parser = argparse.ArgumentParser()
    parser.add_argument("--location", default="valdivia")
    parser.add_argument("--scenario_id", default="baseline")
    parser.add_argument("--mapping", action="store_true", default=True)
    parser.add_argument("--export-pmtiles", dest="export_pmtiles", action="store_true", default=True)
    parser.add_argument("--legacy-plotly", dest="legacy_plotly", action="store_true", default=False)
    args = parser.parse_args([])

    ui = PipelineUI("valdivia", 32719, args=args)
    audit_layout = ui.get_audit_layout(
        census_map={"Total Pop": "total_pop"},
        od_map={"Origin": "h3_origin"},
        spatial_status="VALID"
    )
    # Layout should contain renderables representing the panels
    renderables = audit_layout.renderables
    titles = [getattr(r, "title", None) for r in renderables if hasattr(r, "title")]
    assert any("Pipeline & Mapping Configuration" in str(t) for t in titles)
