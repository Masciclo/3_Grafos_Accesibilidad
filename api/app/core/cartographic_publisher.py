"""
Cartographic Publisher Module (Deep Module)

Consolidates scenario cartography orchestration: PostGIS quantile binning,
bounding box derivation, vector tile layer assembling, and MapLibre/Plotly
viewer generation behind a single, high-leverage interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import glob
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional

from core.workspace_storage import WorkspaceStorage, DiskWorkspaceAdapter, InMemoryWorkspaceAdapter
from core.tile_sources import TileSourceAdapter, LiveMartinTileSource, PMTilesArchiveTileSource
from core.maplibre_maps import MapLibreMapGenerator


@dataclass
class PublishedMapArtifact:
    """Descriptor of published cartographic visualization artifacts."""
    scenario_id: str
    mode: str
    primary_map_path: str
    generated_maps: Dict[str, str] = field(default_factory=dict)
    bbox: List[float] = field(default_factory=list)
    quantiles: List[float] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class CartographicDataAdapter(ABC):
    """Abstract seam decoupling spatial data extraction from map generation."""

    @abstractmethod
    def get_scenario_bbox(
        self, scenario_prefix: str, fallback_bbox: Optional[List[float]] = None
    ) -> List[float]:
        """Derive WGS84 bounding box [min_lon, min_lat, max_lon, max_lat]."""
        pass

    @abstractmethod
    def get_flow_quantiles(self, scenario_prefix: str) -> List[float]:
        """Derive flow quantile break values [p0, p50, p75, p90, p97, max]."""
        pass

    @abstractmethod
    def has_project_infrastructure(self, scenario_prefix: str) -> bool:
        """Check if scenario network contains tagged project edges."""
        pass

    @abstractmethod
    def has_h3_demand(self, scenario_prefix: str) -> bool:
        """Check if scenario has an associated H3 demand table."""
        pass

    @abstractmethod
    def get_h3_purposes_and_p95(self, scenario_prefix: str) -> Dict[str, Optional[float]]:
        """Return available travel demand purposes with their p95 trip values."""
        pass

    @abstractmethod
    def get_max_delta(self, scenario_prefix: str) -> float:
        """Derive maximum absolute delta flow value."""
        pass

    @abstractmethod
    def ensure_database_fixtures(
        self, scenario_prefix: str, city_key: str, storage: WorkspaceStorage
    ) -> None:
        """Deploy MVT functions and ensure context layers in database if applicable."""
        pass


class SyntheticCartographicAdapter(CartographicDataAdapter):
    """
    Synthetic in-memory data adapter for headless tests without PostGIS.
    """

    def __init__(
        self,
        quantiles: Optional[List[float]] = None,
        bbox: Optional[List[float]] = None,
        has_project: bool = True,
        has_h3: bool = True,
        h3_purposes: Optional[List[str]] = None,
        max_delta: float = 500.0,
    ):
        self.quantiles = quantiles or [0.0, 10.0, 25.0, 50.0, 100.0, 500.0]
        self.bbox = bbox or [-70.6693, -33.4489, -70.6693, -33.4489]
        self._has_project = has_project
        self._has_h3 = has_h3
        self.h3_purposes = h3_purposes or ["work", "study"]
        self.max_delta = max_delta

    def get_scenario_bbox(
        self, scenario_prefix: str, fallback_bbox: Optional[List[float]] = None
    ) -> List[float]:
        return self.bbox

    def get_flow_quantiles(self, scenario_prefix: str) -> List[float]:
        return self.quantiles

    def has_project_infrastructure(self, scenario_prefix: str) -> bool:
        return self._has_project

    def has_h3_demand(self, scenario_prefix: str) -> bool:
        return self._has_h3

    def get_h3_purposes_and_p95(self, scenario_prefix: str) -> Dict[str, Optional[float]]:
        if not self._has_h3:
            return {}
        return {p: 120.0 for p in self.h3_purposes}

    def get_max_delta(self, scenario_prefix: str) -> float:
        return self.max_delta

    def ensure_database_fixtures(
        self, scenario_prefix: str, city_key: str, storage: WorkspaceStorage
    ) -> None:
        pass


class DatabaseCartographicAdapter(CartographicDataAdapter):
    """
    PostGIS-backed spatial data adapter.
    Encapsulates raw SQL queries, statistical quantiles, and spatial extents.
    """

    def __init__(self, engine: Any):
        self.engine = engine

    def get_max_delta(self, scenario_prefix: str) -> float:
        from sqlalchemy import text
        for delta_table in [f"{scenario_prefix}_delta_network", f"{scenario_prefix}_delta"]:
            try:
                with self.engine.connect() as conn:
                    delta_exists = conn.execute(text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :t)"
                    ), {"t": delta_table}).fetchone()[0]
                    if delta_exists:
                        d_res = conn.execute(text(f"SELECT COALESCE(MAX(ABS(delta_flow)), 500) FROM {delta_table}")).fetchone()
                        if d_res and d_res[0] is not None:
                            return float(d_res[0])
            except Exception:
                pass
        return 500.0

    def ensure_database_fixtures(
        self, scenario_prefix: str, city_key: str, storage: WorkspaceStorage
    ) -> None:
        from sqlalchemy import text
        # 1. Deploy MVT functions
        try:
            sql_path = Path(__file__).resolve().parent.parent / "sql" / "common" / "create_mvt_functions.sql"
            if sql_path.exists():
                with open(sql_path, "r", encoding="utf-8") as f:
                    sql_code = f.read()
                with self.engine.begin() as conn:
                    conn.execute(text(sql_code))
        except Exception:
            pass

        # 2. Context layers
        try:
            with self.engine.connect() as conn:
                has_ctx = conn.execute(text(
                    f"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = '{city_key}_water')"
                )).fetchone()[0]
            if not has_ctx:
                import geopandas as gpd
                layer_dir = storage.resolve_input("map_layers")
                if layer_dir.exists():
                    for match in glob.glob(str(layer_dir / f"{city_key}_*.geojson")):
                        tbl_base = os.path.basename(match).replace(".geojson", "")
                        try:
                            gdf = gpd.read_file(match)
                            if not gdf.empty:
                                gdf.to_postgis(tbl_base, self.engine, if_exists="replace", index=False)
                                with self.engine.begin() as conn:
                                    conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{tbl_base}_geom ON {tbl_base} USING gist(geometry)"))
                        except Exception:
                            pass
        except Exception:
            pass

    def get_scenario_bbox(
        self, scenario_prefix: str, fallback_bbox: Optional[List[float]] = None
    ) -> List[float]:
        from sqlalchemy import text
        table_name = f"{scenario_prefix}_network"
        try:
            with self.engine.connect() as conn:
                box_query = text(f"""
                    SELECT ST_XMin(b), ST_YMin(b), ST_XMax(b), ST_YMax(b)
                    FROM (SELECT ST_Extent(ST_Transform(geometry, 4326)) AS b FROM {table_name}) sub
                """)
                box_res = conn.execute(box_query).fetchone()
                if box_res and box_res[0] is not None:
                    return [float(box_res[0]), float(box_res[1]), float(box_res[2]), float(box_res[3])]
        except Exception:
            pass
        return fallback_bbox or [-70.6693, -33.4489, -70.6693, -33.4489]

    def get_flow_quantiles(self, scenario_prefix: str) -> List[float]:
        from sqlalchemy import text
        table_name = f"{scenario_prefix}_network"
        try:
            with self.engine.connect() as conn:
                stats_query = text(f"""
                    SELECT 
                        COALESCE(PERCENTILE_CONT(0.0) WITHIN GROUP (ORDER BY od_flow), 0),
                        COALESCE(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY od_flow), 10),
                        COALESCE(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY od_flow), 25),
                        COALESCE(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY od_flow), 50),
                        COALESCE(PERCENTILE_CONT(0.97) WITHIN GROUP (ORDER BY od_flow), 100),
                        COALESCE(MAX(od_flow), 500)
                    FROM {table_name} 
                    WHERE od_flow > 0
                """)
                stats_res = conn.execute(stats_query).fetchone()
                if stats_res and stats_res[5] is not None:
                    return [float(stats_res[i]) for i in range(6)]
        except Exception:
            pass
        return [0.0, 10.0, 25.0, 50.0, 100.0, 500.0]

    def has_project_infrastructure(self, scenario_prefix: str) -> bool:
        from sqlalchemy import text
        table_name = f"{scenario_prefix}_network"
        try:
            with self.engine.connect() as conn:
                has_proj_col = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_schema = 'public' 
                          AND table_name = :t 
                          AND column_name = 'project_id'
                    )
                """), {"t": table_name}).fetchone()[0]
                has_is_proj_col = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_schema = 'public' 
                          AND table_name = :t 
                          AND column_name = 'is_project'
                    )
                """), {"t": table_name}).fetchone()[0]

                if has_is_proj_col and has_proj_col:
                    return conn.execute(text(
                        f"SELECT EXISTS (SELECT 1 FROM {table_name} WHERE is_project = TRUE OR (project_id IS NOT NULL AND project_id != ''))"
                    )).fetchone()[0]
                elif has_is_proj_col:
                    return conn.execute(text(
                        f"SELECT EXISTS (SELECT 1 FROM {table_name} WHERE is_project = TRUE)"
                    )).fetchone()[0]
                elif has_proj_col:
                    return conn.execute(text(
                        f"SELECT EXISTS (SELECT 1 FROM {table_name} WHERE project_id IS NOT NULL AND project_id != '')"
                    )).fetchone()[0]
        except Exception:
            pass
        return False

    def has_h3_demand(self, scenario_prefix: str) -> bool:
        from sqlalchemy import text
        table_name = f"{scenario_prefix}_h3"
        try:
            with self.engine.connect() as conn:
                return conn.execute(text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :t)"
                ), {"t": table_name}).fetchone()[0]
        except Exception:
            return False

    def get_h3_purposes_and_p95(self, scenario_prefix: str) -> Dict[str, Optional[float]]:
        from sqlalchemy import text
        table_name = f"{scenario_prefix}_h3"
        purposes = ["work", "study", "shopping", "personal", "recreational", "returning_home"]
        results: Dict[str, Optional[float]] = {}
        try:
            with self.engine.connect() as conn:
                for purp in purposes:
                    col_exists = conn.execute(text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = :t AND column_name = :c)"
                    ), {"t": table_name, "c": f"trips_{purp}"}).fetchone()[0]
                    if col_exists:
                        p95_res = conn.execute(text(
                            f"SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY trips_{purp}) FROM {table_name} WHERE trips_{purp} > 0"
                        )).fetchone()
                        results[purp] = float(p95_res[0]) if (p95_res and p95_res[0] is not None) else None
        except Exception:
            pass
        return results


class CartographicPublisher:
    """
    Cartographic Publisher (Deep Module).

    Single authoritative interface for publishing scenario map collections.
    Hides PostGIS quantile calculations, layer assembly, and client template compilation.
    """

    def __init__(
        self,
        storage: Optional[WorkspaceStorage] = None,
        data_adapter: Optional[CartographicDataAdapter] = None,
        tile_source: Optional[TileSourceAdapter] = None,
    ):
        self.storage = storage or WorkspaceStorage()
        self.data_adapter = data_adapter or SyntheticCartographicAdapter()
        self.tile_source = tile_source or LiveMartinTileSource()

    def publish_scenario(
        self,
        scenario_prefix: str,
        city_key: str,
        bbox: Optional[List[float]] = None,
        mode: str = "maplibre",
        reference_scenario: Optional[str] = None,
        export_pmtiles: bool = False,
        total_trips: float = 1.0,
        imp_weights: Optional[Dict[str, float]] = None,
        layer_spec: Optional[Dict[str, bool]] = None,
        output_target: Optional[Union[Path, str]] = None,
        observer: Optional[Any] = None,
    ) -> PublishedMapArtifact:
        """
        Publishes the full cartographic suite for a scenario.
        Returns a PublishedMapArtifact describing the generated maps.
        """
        # Ensure database context & MVT functions
        self.data_adapter.ensure_database_fixtures(scenario_prefix, city_key, self.storage)

        # 1. Resolve BBOX & Flow Quantiles
        wgs_bbox = self.data_adapter.get_scenario_bbox(scenario_prefix, fallback_bbox=bbox)
        quantiles = self.data_adapter.get_flow_quantiles(scenario_prefix)
        max_flow = quantiles[5] if len(quantiles) > 5 else 500.0
        p50_flow = quantiles[1] if len(quantiles) > 1 else 10.0

        # Handle storage output directory
        is_memory_storage = isinstance(self.storage.adapter, InMemoryWorkspaceAdapter)
        if output_target:
            map_out_dir = str(output_target)
        elif is_memory_storage:
            temp_dir = tempfile.mkdtemp()
            map_out_dir = temp_dir
        else:
            map_out_dir = str(self.storage.stage_output("maps", city_key=city_key))

        generated_maps: Dict[str, str] = {}

        # 2. Legacy Plotly Mode (Encapsulated Adapter)
        if mode == "legacy":
            from core.academic_maps import AcademicMapGenerator
            generator = AcademicMapGenerator(output_dir=map_out_dir)
            report_path = generator.compile_report(scenario_prefix, [], project_metrics={})
            generated_maps["report"] = report_path
            return PublishedMapArtifact(
                scenario_id=scenario_prefix,
                mode="legacy",
                primary_map_path=report_path,
                generated_maps=generated_maps,
                bbox=wgs_bbox,
                quantiles=quantiles,
                metadata={"total_trips": total_trips},
            )

        # 3. Modern MapLibre Vector Tile Mode
        tile_source = self.tile_source
        if export_pmtiles and not isinstance(tile_source, PMTilesArchiveTileSource):
            tile_source = PMTilesArchiveTileSource(output_dir=map_out_dir)

        if export_pmtiles:
            tile_source.bake_offline_archive(scenario_prefix, wgs_bbox)

        ml_generator = MapLibreMapGenerator(output_dir=map_out_dir, tile_source=tile_source)

        def _persist_map(key: str, local_path: str) -> str:
            if is_memory_storage and os.path.exists(local_path):
                with open(local_path, "r", encoding="utf-8") as f:
                    content = f.read()
                filename = os.path.basename(local_path)
                virtual_dest = self.storage.stage_output("maps", city_key=city_key, scenario_id=scenario_prefix, filename=filename)
                self.storage.write_text(virtual_dest, content)
                return str(virtual_dest)
            return local_path

        # A. Network Flow Map
        if layer_spec is None or layer_spec.get("flow", True):
            flow_path = ml_generator.generate_flow_map(
                scenario_prefix=scenario_prefix,
                bbox=wgs_bbox,
                total_trips=total_trips,
                max_flow=max_flow,
                p50_flow=p50_flow,
                city_key=city_key,
                quantiles=quantiles,
            )
            generated_maps["flow"] = _persist_map("flow", flow_path)

        # B. Bikelanes Flow Map
        if layer_spec is None or layer_spec.get("bikelanes", True):
            bikelanes_path = ml_generator.generate_bikelanes_flow_map(
                scenario_prefix=scenario_prefix,
                bbox=wgs_bbox,
                total_trips=total_trips,
                max_flow=max_flow,
                p50_flow=p50_flow,
                city_key=city_key,
                quantiles=quantiles,
            )
            generated_maps["bikelanes"] = _persist_map("bikelanes", bikelanes_path)

        # C. Project Performance Map (if project edges exist)
        if (layer_spec is None or layer_spec.get("project_performance", True)) and self.data_adapter.has_project_infrastructure(scenario_prefix):
            perf_path = ml_generator.generate_project_performance_map(
                scenario_prefix=scenario_prefix,
                bbox=wgs_bbox,
                total_trips=total_trips,
                max_flow=max_flow,
                p50_flow=p50_flow,
                city_key=city_key,
                quantiles=quantiles,
            )
            generated_maps["project_performance"] = _persist_map("project_performance", perf_path)

        # D. H3 Travel Demand Purpose Maps
        if (layer_spec is None or layer_spec.get("h3", True)) and self.data_adapter.has_h3_demand(scenario_prefix):
            purposes = self.data_adapter.get_h3_purposes_and_p95(scenario_prefix)
            for purp, p95_val in purposes.items():
                if layer_spec is not None and not layer_spec.get(f"h3_{purp}", True):
                    continue
                try:
                    h3_path = ml_generator.generate_h3_purpose_map(
                        scenario_prefix=scenario_prefix,
                        bbox=wgs_bbox,
                        purpose=purp,
                        p95=p95_val,
                        city_key=city_key,
                    )
                    generated_maps[f"h3_{purp}"] = _persist_map(f"h3_{purp}", h3_path)
                except Exception:
                    pass

        # E. Impedance Map
        if layer_spec is None or layer_spec.get("impedance", True):
            weights = imp_weights or {
                "primary": 15.0,
                "secondary": 7.0,
                "tertiary": 3.0,
                "local": 1.5,
                "bike": 0.5,
            }
            imp_path = ml_generator.generate_impedance_map(
                scenario_prefix=scenario_prefix,
                city_key=city_key,
                bbox=wgs_bbox,
                imp_weights=weights,
            )
            generated_maps["impedance"] = _persist_map("impedance", imp_path)

        if observer:
            observer.on_progress_update(None, "ADVANCE_MAPPING", increment=1)

        # F. Delta & Compare Maps (if reference scenario given)
        if reference_scenario:
            try:
                max_delta = self.data_adapter.get_max_delta(scenario_prefix)
                delta_path = ml_generator.generate_delta_map(
                    scenario_prefix=scenario_prefix,
                    bbox=wgs_bbox,
                    max_delta=max_delta,
                    city_key=city_key,
                )
                generated_maps["delta"] = _persist_map("delta", delta_path)

                compare_path = ml_generator.generate_compare_map(
                    scenario_prefix=scenario_prefix,
                    reference_scenario_prefix=reference_scenario,
                    bbox=wgs_bbox,
                    city_key=city_key,
                    max_flow=max_flow,
                    p50_flow=p50_flow,
                    quantiles=quantiles,
                )
                generated_maps["compare"] = _persist_map("compare", compare_path)
            except Exception:
                pass

        return PublishedMapArtifact(
            scenario_id=scenario_prefix,
            mode="maplibre",
            primary_map_path=generated_maps.get("flow", ""),
            generated_maps=generated_maps,
            bbox=wgs_bbox,
            quantiles=quantiles,
            metadata={
                "total_trips": total_trips,
                "city_key": city_key,
                "export_pmtiles": export_pmtiles,
            },
        )
