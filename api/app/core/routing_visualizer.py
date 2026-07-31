import os
import traceback
from enum import Enum
from typing import Dict, Any, Optional, Protocol, List, Tuple
from dataclasses import dataclass
import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine, text
from ui.components import diagnostic_handler

class MapType(Enum):
    IMPEDANCE = "impedance"
    FLOW = "flow"
    FLOW_BIKELANES = "flow_bikelanes"
    DELTA_SIGMA = "delta_sigma"
    PROJECT_PERFORMANCE = "project_performance"

BoundingBox = Tuple[float, float, float, float]  # (xmin, ymin, xmax, ymax)

@dataclass(frozen=True)
class RenderedPlot:
    map_type: MapType
    raw_html_content: str
    bounding_box: BoundingBox
    file_path: str

@dataclass(frozen=True)
class ReportOutput:
    destination_uri: str
    export_successful: bool
    size_bytes: int
    metadata: Dict[str, str]

class VisualStyleProvider(Protocol):
    def get_layout_config(self) -> Dict[str, Any]:
        ...
    def get_color_scale(self, map_type: MapType) -> List[str]:
        ...

class ExportDestination(Protocol):
    def export(self, payload: str, filename_hint: str) -> str:
        ...

class StandardAcademicStyleProvider:
    """
    Standard visual style for academic publications.
    """
    def __init__(self, font_family: str = "Serif"):
        self.font_family = font_family

    def get_layout_config(self) -> Dict[str, Any]:
        return {"font_family": self.font_family}

    def get_color_scale(self, map_type: MapType) -> List[str]:
        return []

class LocalHTMLExportAdapter:
    """
    Export destination to write output files on local workspace paths.
    """
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def export(self, payload: str, filename_hint: str) -> str:
        path = os.path.join(self.output_dir, filename_hint)
        with open(path, "w", encoding='utf-8') as f:
            f.write(payload)
        return path

class AcademicReporter:
    """
    Deep Module encapsulating Plotly chart layers and map exports.
    """
    def __init__(self, style_provider: VisualStyleProvider, exporter: ExportDestination, observer: Optional[Any] = None):
        self.style_provider = style_provider
        self.exporter = exporter
        self.observer = observer

    def generate_map(
        self, 
        network_gdf: gpd.GeoDataFrame, 
        map_type: MapType, 
        bbox: BoundingBox, 
        scenario_id: str,
        total_trips: float = 1.0,
        context_gdf: Optional[gpd.GeoDataFrame] = None
    ) -> RenderedPlot:
        """
        Generates an individual high-fidelity map file by delegating to mapping libraries.
        """
        from core.academic_maps import AcademicMapGenerator
        output_dir = getattr(self.exporter, 'output_dir', 'data/maps')
        generator = AcademicMapGenerator(output_dir=output_dir)
        
        path = ""
        if map_type == MapType.IMPEDANCE:
            path = generator.generate_impedance_map(network_gdf, scenario_id, bbox=bbox)
        elif map_type == MapType.FLOW:
            path = generator.generate_flow_map(network_gdf, scenario_id, type="flow", bbox=bbox, total_trips=total_trips, flow_type="all")
        elif map_type == MapType.FLOW_BIKELANES:
            path = generator.generate_flow_map(network_gdf, scenario_id, type="flow", bbox=bbox, total_trips=total_trips, flow_type="bikelanes")
        elif map_type == MapType.DELTA_SIGMA:
            path = generator.generate_delta_sigma_map(network_gdf, scenario_id, bbox=bbox, context_gdf=context_gdf)
        elif map_type == MapType.PROJECT_PERFORMANCE:
            path = generator.generate_project_performance_map(network_gdf, scenario_id, bbox=bbox, total_trips=total_trips)

        html = ""
        if path and os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                html = f.read()

        return RenderedPlot(
            map_type=map_type,
            raw_html_content=html,
            bounding_box=bbox,
            file_path=path
        )

    def compile_report(
        self, 
        plots: List[RenderedPlot], 
        scenario_id: str, 
        title: str,
        project_metrics: Optional[Dict[str, Any]] = None
    ) -> ReportOutput:
        """
        Compiles multiple maps into a single responsive layout.
        """
        from core.academic_maps import AcademicMapGenerator
        output_dir = getattr(self.exporter, 'output_dir', 'data/maps')
        generator = AcademicMapGenerator(output_dir=output_dir)
        
        map_paths = [p.file_path if p else None for p in plots]
        path = generator.compile_report(scenario_id, map_paths, project_metrics=project_metrics)
        
        size = 0
        if path and os.path.exists(path):
            size = os.path.getsize(path)
            
        return ReportOutput(
            destination_uri=path,
            export_successful=True,
            size_bytes=size,
            metadata={}
        )

class RoutingVisualizer:
    """
    Backward-compatible task interface running on ScenarioContext.
    """
    def __init__(self, context):
        self.context = context

    def execute(self) -> None:
        config = self.context.config
        tables = self.context.tables
        db_cfg = self.context.db_config
        observer = self.context.observer
        
        from infra.ingestion import create_abbreviation
        loc_abbr = create_abbreviation(config.location)
        scenario_prefix = f"{loc_abbr}_{config.scenario_id}"
        total_trips = self.context.state.get('total_trips', 1.0)
        
        diagnostic_handler.report("MAPPING", "INFO", f"Generating synchronized dashboard for {scenario_prefix}...")
        
        if observer:
            observer.on_progress_update(9, "RUNNING", "Academic Mapping (Visuals)")

        try:
            if db_cfg:
                user, password, host, port, db = db_cfg.get('user'), db_cfg.get('password'), db_cfg.get('host'), db_cfg.get('port'), db_cfg.get('name')
            else:
                user, password, host, port, db = os.getenv('DB_USER'), os.getenv('DB_PASSWORD'), os.getenv('HOST'), os.getenv('PORT'), os.getenv('DATABASE_NAME')
                
            engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{db}')
            
            output_loc = config.city_key if config.city_key else loc_abbr
            style_provider = StandardAcademicStyleProvider(font_family="Serif")
            exporter = LocalHTMLExportAdapter(output_dir=f"data/{output_loc}/out/maps")
            
            reporter = AcademicReporter(style_provider, exporter, observer)
            
            final_net_table = f"{scenario_prefix}_network"
            
            # Check the size of the network table first to optimize loading on large cities like Santiago
            with engine.connect() as conn:
                count_res = conn.execute(text(f"SELECT COUNT(*) FROM {final_net_table}")).fetchone()
                net_size = count_res[0] if count_res else 0
                
            if net_size > 50000:
                diagnostic_handler.report("LARGE_NETWORK_MAPPING", "INFO", f"Large network detected ({net_size} edges). Filtering background streets within 1.5km of active corridors...")
                query = f"""
                    SELECT * FROM {final_net_table} 
                    WHERE od_flow > 0 
                       OR is_project = TRUE
                       OR highway IN ('primary', 'secondary', 'tertiary', 'cycleway', 'trunk', 'motorway')
                       OR original_highway IN ('primary', 'secondary', 'tertiary', 'cycleway', 'trunk', 'motorway')
                       OR ST_DWithin(
                            geometry,
                            (
                                SELECT ST_Union(geometry) 
                                FROM {final_net_table} 
                                WHERE od_flow > 0 OR is_project = TRUE
                            ),
                            1500
                       )
                """
            else:
                query = f"SELECT * FROM {final_net_table}"
                
            net_gdf = gpd.read_postgis(query, engine, geom_col='geometry')
            
            mask_col = 'participating_in_analysis'
            mcp_gdf = net_gdf[net_gdf[mask_col] == True] if mask_col in net_gdf.columns else net_gdf
            master_bbox = mcp_gdf.total_bounds
            
            # Generate Impedance
            reporter.generate_map(net_gdf, MapType.IMPEDANCE, master_bbox, scenario_prefix)
            if observer:
                observer.on_progress_update(None, "ADVANCE_MAPPING", increment=1)
                
            # Generate active scenario flow maps: full network flow & bikelane flow for all scenarios
            net_flow_plot = reporter.generate_map(net_gdf, MapType.FLOW, master_bbox, scenario_prefix, total_trips)
            bikelane_flow_plot = reporter.generate_map(net_gdf, MapType.FLOW_BIKELANES, master_bbox, scenario_prefix, total_trips)
            
            # Generate Project Performance Map if projects or recommendations are present
            has_projects = bool(config.projects_input or config.scenario_id.startswith("rec_") or ('is_project' in net_gdf.columns and net_gdf['is_project'].any()))
            if has_projects:
                reporter.generate_map(net_gdf, MapType.PROJECT_PERFORMANCE, master_bbox, scenario_prefix, total_trips)
            
            plots = []
            
            # Map 0: Baseline Flow (Red Completa)
            base_gdf = None
            if config.reference_scenario:
                try:
                    base_table = f"{loc_abbr}_{config.reference_scenario}_network"
                    base_gdf = gpd.read_postgis(f"SELECT * FROM {base_table}", engine, geom_col='geometry')
                except Exception:
                    pass

            if base_gdf is not None and not base_gdf.empty:
                plots.append(reporter.generate_map(base_gdf, MapType.FLOW, master_bbox, f"{loc_abbr}_{config.reference_scenario}", total_trips))
                # Map 1: Baseline Flow (Ciclovías)
                plots.append(reporter.generate_map(base_gdf, MapType.FLOW_BIKELANES, master_bbox, f"{loc_abbr}_{config.reference_scenario}", total_trips))
            else:
                plots.append(None)
                plots.append(None)

            # Map 2: Project Scenario Flow (Red Completa)
            plots.append(net_flow_plot)
            
            # Map 3: Delta Flow
            delta_table = f"{scenario_prefix}_delta_network"
            with self.context.conn.cursor() as cur:
                cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s)", (delta_table,))
                delta_exists = cur.fetchone()[0]
                
            if delta_exists:
                delta_gdf = gpd.read_postgis(f"SELECT * FROM {delta_table}", engine, geom_col='geometry')
                plots.append(reporter.generate_map(delta_gdf, MapType.DELTA_SIGMA, master_bbox, scenario_prefix, context_gdf=net_gdf))
            else:
                plots.append(None)

            # Query project metrics if projects exist
            project_metrics = None
            if config.projects_input:
                try:
                    with engine.connect() as conn:
                        len_res = conn.execute(text(f"SELECT SUM(length) FROM {tables['net']} WHERE is_project = TRUE")).fetchone()
                        total_len = float(len_res[0]) if len_res and len_res[0] is not None else 0.0
                        
                        flow_res = conn.execute(text(f"SELECT AVG(od_flow), MAX(od_flow) FROM {tables['net']} WHERE is_project = TRUE")).fetchone()
                        avg_flow = float(flow_res[0]) if flow_res and flow_res[0] is not None else 0.0
                        max_flow = float(flow_res[1]) if flow_res and flow_res[1] is not None else 0.0
                        
                        total_cost = total_len * 100.0
                        pcr = (max_flow / total_trips) * 100.0 if total_trips > 0 else 0.0
                        
                        project_metrics = {
                            "length": total_len,
                            "cost": total_cost,
                            "avg_flow": avg_flow,
                            "max_flow": max_flow,
                            "pcr": pcr
                        }
                except Exception as e:
                    diagnostic_handler.report("METRICS_EXTRACTION_FAILED", "WARNING", f"Could not extract project metrics: {e}")

            # Compile consolidated report dashboard
            if config.reference_scenario and plots[0] is not None:
                reporter.compile_report(plots, scenario_prefix, "Academic Impact Report", project_metrics=project_metrics)

            # Generate Standalone H3 Purpose Maps dynamically
            h3_table = f"{scenario_prefix}_h3"
            with self.context.conn.cursor() as cur:
                cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s)", (h3_table,))
                h3_exists = cur.fetchone()[0]
                
            if h3_exists:
                try:
                    h3_gdf = gpd.read_postgis(f"SELECT * FROM {h3_table}", engine, geom_col='geometry')
                    h3_purpose_cols = [c for c in h3_gdf.columns if c.startswith('trips_') and c != 'trips']
                    
                    if h3_purpose_cols:
                        from core.academic_maps import AcademicMapGenerator
                        generator = AcademicMapGenerator(output_dir=getattr(reporter.exporter, 'output_dir', 'data/maps'))
                        
                        # Map specific trip purposes to sequential ColorBrewer color scales
                        purpose_colorscales = {
                            'trips_work': 'OrRd',
                            'trips_study': 'BuGn',
                            'trips_shopping': 'PuRd',
                            'trips_personal': 'PuBu',
                            'trips_recreational': 'YlGn',
                            'trips_returning_home': 'BuPu'
                        }
                        
                        for idx, col in enumerate(h3_purpose_cols):
                            clean_name = col.replace("trips_", "").replace("_", " ").title()
                            color_rgb = purpose_colorscales.get(col, 'OrRd')
                            
                            generator.generate_h3_purpose_map(
                                h3_gdf, net_gdf, scenario_prefix,
                                column=col,
                                title=f"{clean_name} Trips (H3 Daily Density)",
                                color_rgb=color_rgb,
                                legend_title=clean_name,
                                bbox=master_bbox
                            )
                except Exception as map_err:
                    diagnostic_handler.report("H3_MAPPING_FAILED", "WARNING", f"Failed to generate standalone H3 maps: {map_err}")

            # Generate Standalone Flow Purpose Maps dynamically (Option B)
            flow_purpose_table = f"{tables['net']}_flow_by_purpose"
            with self.context.conn.cursor() as cur:
                cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s)", (flow_purpose_table,))
                flow_table_exists = cur.fetchone()[0]
                
            if flow_table_exists:
                try:
                    with self.context.conn.cursor() as cur:
                        cur.execute(f"SELECT DISTINCT purpose FROM {flow_purpose_table}")
                        active_purposes = [row[0] for row in cur.fetchall()]
                        
                    if active_purposes:
                        from core.academic_maps import AcademicMapGenerator
                        generator = AcademicMapGenerator(output_dir=getattr(reporter.exporter, 'output_dir', 'data/maps'))
                        
                        # Banner color palette
                        banner_colors = [
                            (131, 56, 236),  # Purple (#8338ec)
                            (58, 134, 255),  # Blue (#3a86ff)
                            (255, 0, 110),   # Hot Pink (#ff006e)
                            (251, 86, 7),    # Orange-Red (#fb5607)
                            (255, 190, 11)   # Amber Yellow (#ffbe0b)
                        ]
                        
                        for idx, purpose in enumerate(active_purposes):
                            # Load flow values for this purpose and join with net_gdf
                            flow_df = pd.read_sql(f"SELECT edge_id, flow FROM {flow_purpose_table} WHERE purpose = '{purpose}'", engine)
                            # Merge flow into net_gdf copy on edge_id
                            purpose_net_gdf = net_gdf.merge(flow_df.rename(columns={'flow': 'purpose_flow'}), on='edge_id', how='left')
                            purpose_net_gdf['purpose_flow'] = purpose_net_gdf['purpose_flow'].fillna(0.0)
                            
                            clean_name = purpose.replace("_", " ").title()
                            color_rgb = banner_colors[idx % len(banner_colors)]
                            
                            generator.generate_flow_purpose_map(
                                purpose_net_gdf, net_gdf, scenario_prefix,
                                column='purpose_flow',
                                title=f"{clean_name} Trip Flow (Betweenness Centrality)",
                                color_rgb=color_rgb,
                                legend_title=clean_name,
                                bbox=master_bbox
                            )
                except Exception as flow_map_err:
                    diagnostic_handler.report("FLOW_PURPOSE_MAPPING_FAILED", "WARNING", f"Failed to generate purpose flow maps: {flow_map_err}")

        except Exception as e:
            diagnostic_handler.report("MAPPING_FAILED", "ERROR", f"Mapping failed: {e} | {traceback.format_exc().splitlines()[-1]}")

        if observer:
            observer.on_progress_update(9, "DONE ✅")
