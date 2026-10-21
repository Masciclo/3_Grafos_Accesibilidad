import os
import pytest
from core.workspace_storage import WorkspaceStorage, InMemoryWorkspaceAdapter
from core.tile_sources import MockTileSource
from core.cartographic_publisher import (
    CartographicPublisher,
    SyntheticCartographicAdapter,
    PublishedMapArtifact,
)

def test_cartographic_publisher_maplibre_synthetic():
    # Setup test adapters (in-memory storage + mock tile source + synthetic spatial adapter)
    storage = WorkspaceStorage(adapter=InMemoryWorkspaceAdapter())
    tile_source = MockTileSource()
    data_adapter = SyntheticCartographicAdapter(
        quantiles=[0.0, 15.0, 35.0, 75.0, 150.0, 800.0],
        bbox=[-70.7, -33.5, -70.6, -33.4],
        has_project=True,
        has_h3=True,
        h3_purposes=["work", "study"]
    )

    publisher = CartographicPublisher(
        storage=storage,
        tile_source=tile_source,
        data_adapter=data_adapter
    )

    artifact = publisher.publish_scenario(
        scenario_prefix="stgo_interv_1",
        city_key="santiago",
        mode="maplibre"
    )

    assert isinstance(artifact, PublishedMapArtifact)
    assert artifact.scenario_id == "stgo_interv_1"
    assert artifact.mode == "maplibre"
    assert artifact.quantiles == [0.0, 15.0, 35.0, 75.0, 150.0, 800.0]
    assert artifact.bbox == [-70.7, -33.5, -70.6, -33.4]

    # Verify maps generated
    maps = artifact.generated_maps
    assert "flow" in maps
    assert "bikelanes" in maps
    assert "impedance" in maps
    assert "project_performance" in maps
    assert "h3_work" in maps
    assert "h3_study" in maps

    # Verify that primary map HTML was written to storage
    flow_html = storage.read_text(maps["flow"])
    assert "maplibregl" in flow_html
    assert "mock://tiles/stgo_interv_1" in flow_html
    assert "800.0" in flow_html or "800" in flow_html

def test_cartographic_publisher_missing_optional_layers():
    storage = WorkspaceStorage(adapter=InMemoryWorkspaceAdapter())
    tile_source = MockTileSource()
    data_adapter = SyntheticCartographicAdapter(
        quantiles=[0.0, 10.0, 20.0, 50.0, 100.0, 300.0],
        bbox=[-70.7, -33.5, -70.6, -33.4],
        has_project=False,
        has_h3=False
    )

    publisher = CartographicPublisher(
        storage=storage,
        tile_source=tile_source,
        data_adapter=data_adapter
    )

    artifact = publisher.publish_scenario(
        scenario_prefix="stgo_baseline",
        city_key="santiago",
        mode="maplibre"
    )

    assert "flow" in artifact.generated_maps
    assert "impedance" in artifact.generated_maps
    assert "project_performance" not in artifact.generated_maps
    assert "h3_work" not in artifact.generated_maps

def test_cartographic_publisher_layer_spec_and_output_target(tmp_path):
    storage = WorkspaceStorage(adapter=InMemoryWorkspaceAdapter())
    tile_source = MockTileSource()
    data_adapter = SyntheticCartographicAdapter(
        quantiles=[0.0, 10.0, 20.0, 50.0, 100.0, 300.0],
        bbox=[-70.7, -33.5, -70.6, -33.4],
        has_project=True,
        has_h3=True,
        h3_purposes=["work", "study"]
    )

    publisher = CartographicPublisher(
        storage=storage,
        tile_source=tile_source,
        data_adapter=data_adapter
    )

    # Only request flow and bikelanes
    artifact = publisher.publish_scenario(
        scenario_prefix="stgo_custom",
        city_key="santiago",
        mode="maplibre",
        layer_spec={"flow": True, "bikelanes": True, "impedance": False, "project_performance": False, "h3": False},
        output_target=tmp_path
    )

    assert "flow" in artifact.generated_maps
    assert "bikelanes" in artifact.generated_maps
    assert "impedance" not in artifact.generated_maps
    assert "project_performance" not in artifact.generated_maps
    assert "h3_work" not in artifact.generated_maps
    assert (tmp_path / "stgo_custom_flow.html").exists()
