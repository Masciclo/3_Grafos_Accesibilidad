import os
import pytest
from pathlib import Path
from core.workspace_storage import (
    WorkspaceStorage,
    DiskWorkspaceAdapter,
    InMemoryWorkspaceAdapter,
)

def test_in_memory_workspace_adapter_roundtrip():
    adapter = InMemoryWorkspaceAdapter()
    storage = WorkspaceStorage(adapter=adapter)
    
    # Stage output artifact
    virtual_path = storage.stage_output(
        key="maps",
        city_key="santiago",
        scenario_id="interv_1",
        filename="flow_map.html"
    )
    assert "santiago" in str(virtual_path)
    assert "flow_map.html" in str(virtual_path)
    
    # Write and read text
    test_content = "<html><body>Map content</body></html>"
    storage.write_text(virtual_path, test_content)
    
    assert storage.exists(virtual_path)
    assert storage.read_text(virtual_path) == test_content
    
    # Check listing artifacts
    files = storage.list_files(key="maps", city_key="santiago", scenario_id="interv_1")
    assert any("flow_map.html" in f for f in files)

    # Test logical key read/write artifact
    art_path = storage.write_artifact(
        key="maps",
        scenario_id="interv_1",
        city_key="santiago",
        filename="summary.json",
        data='{"status": "ok"}'
    )
    assert storage.read_artifact(key="maps", scenario_id="interv_1", city_key="santiago", filename="summary.json") == '{"status": "ok"}'

def test_disk_workspace_adapter_canonical_resolution(tmp_path):
    # Pass an explicit root to simulate canonical repo root
    adapter = DiskWorkspaceAdapter(root_dir=tmp_path)
    storage = WorkspaceStorage(adapter=adapter)
    
    assert storage.root_dir == tmp_path
    assert storage.data_dir == tmp_path / "data"
    
    # Initialize city structure
    storage.initialize_city_structure("santiago")
    expected_subdirs = [
        tmp_path / "data" / "santiago" / "raw",
        tmp_path / "data" / "santiago" / "proc",
        tmp_path / "data" / "santiago" / "out" / "maps",
        tmp_path / "data" / "santiago" / "out" / "qgis",
    ]
    for sub in expected_subdirs:
        assert sub.exists() and sub.is_dir()
        
    # Stage output path
    out_file = storage.stage_output(
        key="maps",
        city_key="santiago",
        scenario_id="scenario_01",
        filename="impedance_map.html"
    )
    assert str(out_file).startswith(str(tmp_path / "data" / "santiago"))
    
    storage.write_text(out_file, "<div>Map</div>")
    assert out_file.exists()
    assert storage.read_text(out_file) == "<div>Map</div>"

def test_workspace_storage_default_anchor_detection():
    # When initialized without root_dir, it automatically detects project root
    adapter = DiskWorkspaceAdapter()
    storage = WorkspaceStorage(adapter=adapter)
    assert storage.root_dir.exists()
    assert (storage.root_dir / "grafos-accesibilidad").exists() or (storage.root_dir / "api").exists()
