import os
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

class TileSourceAdapter(ABC):
    """
    TileSourceAdapter: Abstract domain seam decoupling map visualization
    from the underlying vector tile transport mechanism (live server vs static archive).
    """
    @abstractmethod
    def get_network_source(self, scenario_prefix: str) -> Dict[str, Any]:
        """Returns the MapLibre source JSON block for network flow & hierarchy tiles."""
        pass

    @abstractmethod
    def get_delta_source(self, scenario_prefix: str) -> Dict[str, Any]:
        """Returns the MapLibre source JSON block for delta sigma (ΔF) flow tiles."""
        pass

    @abstractmethod
    def get_context_source(self, city_key: str) -> Dict[str, Any]:
        """Returns the MapLibre source JSON block for local context (water, green, boundary) tiles."""
        pass

    @abstractmethod
    def get_h3_source(self, scenario_prefix: str) -> Dict[str, Any]:
        """Returns the MapLibre source JSON block for H3 hexagonal purpose density tiles."""
        pass

    @abstractmethod
    def bake_offline_archive(self, scenario_prefix: str, bbox: List[float], conn: Optional[Any] = None) -> Optional[str]:
        """Bakes static tile archive if supported by this adapter."""
        pass

class LiveMartinTileSource(TileSourceAdapter):
    """
    LiveMartinTileSource: Streams dynamic MVT tiles on-the-fly from the Martin tile server
    connected to PostGIS. Zero intermediate compilation delay.
    """
    def __init__(self, host: str = "http://localhost:3000"):
        # Strip trailing slash if present
        self.host = host.rstrip("/")

    def get_network_source(self, scenario_prefix: str) -> Dict[str, Any]:
        return {
            "type": "vector",
            "tiles": [f"{self.host}/mvt_network/{{z}}/{{x}}/{{y}}?scenario={scenario_prefix}"],
            "minzoom": 0,
            "maxzoom": 18
        }

    def get_delta_source(self, scenario_prefix: str) -> Dict[str, Any]:
        return {
            "type": "vector",
            "tiles": [f"{self.host}/mvt_delta/{{z}}/{{x}}/{{y}}?scenario={scenario_prefix}"],
            "minzoom": 0,
            "maxzoom": 18
        }

    def get_context_source(self, city_key: str) -> Dict[str, Any]:
        return {
            "type": "vector",
            "tiles": [f"{self.host}/mvt_context/{{z}}/{{x}}/{{y}}?city_key={city_key}"],
            "minzoom": 0,
            "maxzoom": 18
        }

    def get_h3_source(self, scenario_prefix: str) -> Dict[str, Any]:
        return {
            "type": "vector",
            "tiles": [f"{self.host}/mvt_h3/{{z}}/{{x}}/{{y}}?scenario={scenario_prefix}"],
            "minzoom": 0,
            "maxzoom": 18
        }

    def bake_offline_archive(self, scenario_prefix: str, bbox: List[float], conn: Optional[Any] = None) -> Optional[str]:
        # Live mode does not bake static files
        return None

class PMTilesArchiveTileSource(TileSourceAdapter):
    """
    PMTilesArchiveTileSource: Reads tiles client-side from a single-file .pmtiles archive
    via HTTP range requests. Supports offline sharing and serverless distribution.
    """
    def __init__(self, output_dir: str = "data/maps"):
        self.output_dir = output_dir

    def get_network_source(self, scenario_prefix: str) -> Dict[str, Any]:
        return {
            "type": "vector",
            "url": f"pmtiles://./{scenario_prefix}.pmtiles"
        }

    def get_delta_source(self, scenario_prefix: str) -> Dict[str, Any]:
        return {
            "type": "vector",
            "url": f"pmtiles://./{scenario_prefix}.pmtiles"
        }

    def get_context_source(self, city_key: str) -> Dict[str, Any]:
        return {
            "type": "vector",
            "url": f"pmtiles://./{city_key}_context.pmtiles"
        }

    def get_h3_source(self, scenario_prefix: str) -> Dict[str, Any]:
        return {
            "type": "vector",
            "url": f"pmtiles://./{scenario_prefix}_h3.pmtiles"
        }

    def bake_offline_archive(
        self,
        scenario_prefix: str,
        bbox: List[float],
        conn: Optional[Any] = None,
        martin_container: str = "martin",
        db_url: str = "postgres://ciclo:ciclo@stationdb:5432/ciclo_dev"
    ) -> Optional[str]:
        import subprocess
        os.makedirs(self.output_dir, exist_ok=True)
        archive_path = os.path.join(self.output_dir, f"{scenario_prefix}.pmtiles")
        min_lon, min_lat, max_lon, max_lat = bbox
        cmd = [
            "docker", "compose", "exec", "-T", martin_container,
            "martin-cp",
            "--source", "mvt_network",
            "--url-query", f"scenario={scenario_prefix}",
            f"--bbox={min_lon},{min_lat},{max_lon},{max_lat}",
            "--min-zoom", "9", "--max-zoom", "16",
            "-o", f"/app/{archive_path}",
            db_url
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            return archive_path
        except Exception as e:
            try:
                from ui.components import diagnostic_handler
                diagnostic_handler.report("PMTILES_EXPORT_FAILED", "ERROR", f"Failed to bake archive: {e}")
            except ImportError:
                pass
            return None


class MockTileSource(TileSourceAdapter):
    """
    MockTileSource: Synthetic in-memory tile source adapter for headless tests.
    """
    def __init__(self, base_url: str = "mock://tiles"):
        self.base_url = base_url.rstrip("/")

    def get_network_source(self, scenario_prefix: str) -> Dict[str, Any]:
        return {
            "type": "vector",
            "tiles": [f"{self.base_url}/{scenario_prefix}/{{z}}/{{x}}/{{y}}"],
            "minzoom": 0,
            "maxzoom": 18
        }

    def get_delta_source(self, scenario_prefix: str) -> Dict[str, Any]:
        return {
            "type": "vector",
            "tiles": [f"{self.base_url}/delta/{scenario_prefix}/{{z}}/{{x}}/{{y}}"],
            "minzoom": 0,
            "maxzoom": 18
        }

    def get_context_source(self, city_key: str) -> Dict[str, Any]:
        return {
            "type": "vector",
            "tiles": [f"{self.base_url}/context/{city_key}/{{z}}/{{x}}/{{y}}"],
            "minzoom": 0,
            "maxzoom": 18
        }

    def get_h3_source(self, scenario_prefix: str) -> Dict[str, Any]:
        return {
            "type": "vector",
            "tiles": [f"{self.base_url}/h3/{scenario_prefix}/{{z}}/{{x}}/{{y}}"],
            "minzoom": 0,
            "maxzoom": 18
        }

    def bake_offline_archive(self, scenario_prefix: str, bbox: List[float], conn: Optional[Any] = None) -> Optional[str]:
        return f"{self.base_url}/{scenario_prefix}.pmtiles"
