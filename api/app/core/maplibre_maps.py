import os
import json
import re
from typing import Optional, List, Dict, Any
from core.tile_sources import TileSourceAdapter, LiveMartinTileSource

class MapLibreMapGenerator:
    """
    MapLibreMapGenerator: Produces publication-grade, GPU-accelerated vector map viewers
    using MapLibre GL JS, PostGIS vector tiles, and bijective academic Plotly styling.
    Replaces monolithic multi-megabyte Plotly HTML files with lightweight (< 25 KB) viewers.
    """
    _cached_reducer_script: Optional[str] = None

    def __init__(self, output_dir: str = "data/maps", tile_source: Optional[TileSourceAdapter] = None):
        self.output_dir = output_dir
        self.tile_source = tile_source or LiveMartinTileSource()
        os.makedirs(self.output_dir, exist_ok=True)

    @classmethod
    def _get_reducer_script(cls) -> str:
        if cls._cached_reducer_script is None:
            script_path = os.path.join(os.path.dirname(__file__), "cartography", "ciclo_map_reducer.js")
            if os.path.exists(script_path):
                with open(script_path, "r", encoding="utf-8") as f:
                    content = f.read()
                # Strip multi-line comments and single-line comments for compact delivery
                content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
                content = re.sub(r'//.*', '', content)
                lines = [l.strip() for l in content.splitlines() if l.strip()]
                cls._cached_reducer_script = "\n".join(lines)
            else:
                cls._cached_reducer_script = ""
        return cls._cached_reducer_script

    @staticmethod
    def _get_context_layers() -> List[Dict[str, Any]]:
        return [
            {
                'id': 'context-water',
                'type': 'fill',
                'source': 'context_source',
                'source-layer': 'water',
                'paint': {'fill-color': '#CBE2EE', 'fill-opacity': 0.85}
            },
            {
                'id': 'context-forests',
                'type': 'fill',
                'source': 'context_source',
                'source-layer': 'forests',
                'paint': {'fill-color': '#E8F0E8', 'fill-opacity': 0.80}
            },
            {
                'id': 'context-buildings',
                'type': 'fill',
                'source': 'context_source',
                'source-layer': 'buildings',
                'paint': {'fill-color': '#F0EFEA', 'fill-opacity': 0.90}
            },
            {
                'id': 'context-urban-limit',
                'type': 'line',
                'source': 'context_source',
                'source-layer': 'urban_limit',
                'paint': {'line-color': '#E0E0E0', 'line-width': 1.0, 'line-dasharray': [3, 2]}
            }
        ]

    @staticmethod
    def _get_flow_line_paint(q1: int, q2: int, q3: int, q4: int, q5: int, max_flow: float) -> Dict[str, Any]:
        return {
            'line-color': [
                'case',
                # 1. Project without flow
                ['all', ['==', ['get', 'is_project'], True], ['<=', ['to-number', ['get', 'od_flow']], 0]], '#e67e22',
                # 2. Cycleway without flow: soft reference green
                [
                    'all',
                    ['any', ['==', ['get', 'highway'], 'cycleway'], ['==', ['get', 'original_highway'], 'cycleway']],
                    ['<=', ['to-number', ['get', 'od_flow']], 0]
                ], '#27ae60',
                # 3. Flow > 0: Exact Discrete 5-Quantile Step matching Legend
                ['>', ['to-number', ['get', 'od_flow']], 0], [
                    'step', ['to-number', ['get', 'od_flow']],
                    '#fed976',
                    q1, '#feb24c',
                    q2, '#fd8d3c',
                    q3, '#f03b20',
                    q4, '#bd0026'
                ],
                # 4. Background Hierarchy (od_flow <= 0)
                [
                    'match', ['get', 'highway'],
                    'motorway', '#666666',
                    'trunk', '#888888',
                    'primary', '#888888',
                    'secondary', '#A0A0A0',
                    'tertiary', '#A0A0A0',
                    'residential', '#C8C8C8',
                    'living_street', '#C8C8C8',
                    '#D0D0D0'
                ]
            ],
            'line-width': [
                'interpolate', ['linear'], ['zoom'],
                8, [
                    'case',
                    ['>', ['to-number', ['get', 'od_flow']], 0],
                    ['+', 0.8, ['*', ['min', 1.0, ['/', ['to-number', ['get', 'od_flow']], float(max_flow)]], 2.2]],
                    ['any', ['==', ['get', 'highway'], 'cycleway'], ['==', ['get', 'original_highway'], 'cycleway']], 1.4,
                    ['in', ['get', 'highway'], ['literal', ['motorway', 'trunk']]], 0.8,
                    ['in', ['get', 'highway'], ['literal', ['primary', 'secondary']]], 0.5,
                    0.3
                ],
                11, [
                    'case',
                    ['>', ['to-number', ['get', 'od_flow']], 0],
                    ['+', 1.2, ['*', ['min', 1.0, ['/', ['to-number', ['get', 'od_flow']], float(max_flow)]], 4.0]],
                    ['any', ['==', ['get', 'highway'], 'cycleway'], ['==', ['get', 'original_highway'], 'cycleway']], 2.2,
                    ['in', ['get', 'highway'], ['literal', ['motorway', 'trunk']]], 1.4,
                    ['in', ['get', 'highway'], ['literal', ['primary', 'secondary']]], 0.9,
                    ['==', ['get', 'highway'], 'tertiary'], 0.6,
                    0.4
                ],
                14, [
                    'case',
                    ['>', ['to-number', ['get', 'od_flow']], 0],
                    ['+', 1.8, ['*', ['min', 1.0, ['/', ['to-number', ['get', 'od_flow']], float(max_flow)]], 6.5]],
                    ['any', ['==', ['get', 'highway'], 'cycleway'], ['==', ['get', 'original_highway'], 'cycleway']], 3.5,
                    ['in', ['get', 'highway'], ['literal', ['motorway', 'trunk']]], 2.4,
                    ['in', ['get', 'highway'], ['literal', ['primary', 'secondary']]], 1.8,
                    ['==', ['get', 'highway'], 'tertiary'], 1.3,
                    0.8
                ]
            ],
            'line-opacity': [
                'case',
                ['>', ['to-number', ['get', 'od_flow']], 0], 0.95,
                ['==', ['get', 'is_project'], True], 1.0,
                ['any', ['==', ['get', 'highway'], 'cycleway'], ['==', ['get', 'original_highway'], 'cycleway']], 0.85,
                0.35
            ]
        }

    def generate_flow_map(
        self,
        scenario_prefix: str,
        bbox: List[float],
        total_trips: float = 1.0,
        max_flow: float = 1000.0,
        p50_flow: float = 50.0,
        city_key: Optional[str] = None,
        quantiles: Optional[List[float]] = None
    ) -> str:
        """
        Generates a standalone flow.html MapLibre viewer visualizing network & bikelane flow.
        """
        source_config = self.tile_source.get_network_source(scenario_prefix)
        sources: Dict[str, Any] = {'network_source': source_config}
        is_pmtiles = "pmtiles://" in source_config.get("url", "")

        if quantiles and len(quantiles) >= 6:
            q0, q1, q2, q3, q4, q5 = [int(v) for v in quantiles[:6]]
        else:
            q0 = 0
            q1 = max(1, int(p50_flow))
            q2 = max(q1 + 1, int(p50_flow + (max_flow - p50_flow) * 0.25))
            q3 = max(q2 + 1, int(p50_flow + (max_flow - p50_flow) * 0.55))
            q4 = max(q3 + 1, int(p50_flow + (max_flow - p50_flow) * 0.85))
            q5 = max(q4 + 1, int(max_flow))

        q2 = max(q1 + 1, q2)
        q3 = max(q2 + 1, q3)
        q4 = max(q3 + 1, q4)
        q5 = max(q4 + 1, q5)

        layers: List[Dict[str, Any]] = [
            {
                'id': 'background',
                'type': 'background',
                'paint': {'background-color': '#F8F9FA'}
            }
        ]

        if city_key:
            context_source = self.tile_source.get_context_source(city_key)
            sources['context_source'] = context_source
            if "pmtiles://" in context_source.get("url", ""):
                is_pmtiles = True
            layers.extend(self._get_context_layers())

        layers.append({
            'id': 'network-base',
            'type': 'line',
            'source': 'network_source',
            'source-layer': 'network',
            'paint': self._get_flow_line_paint(q1, q2, q3, q4, q5, max_flow)
        })

        bounds_json = json.dumps(bbox)
        sources_json = json.dumps(sources)
        layers_json = json.dumps(layers)
        reducer_script = self._get_reducer_script()

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>+Ciclo: {scenario_prefix} — Network Flow</title>
    <script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
    <link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet" />
    {"<script src='https://unpkg.com/pmtiles@3.0.7/dist/pmtiles.js'></script>" if is_pmtiles else ""}
    <style>
        body {{ margin: 0; padding: 0; background: #dee2e6; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
        .north-arrow {{
            position: absolute; top: 20px; left: 20px;
            background: rgba(255, 255, 255, 0.90);
            border: 1px solid black; border-radius: 2px; padding: 4px 10px;
            font-family: "Times New Roman", Times, serif; font-size: 16px;
            font-weight: bold; text-align: center; color: black; line-height: 1.1;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15); z-index: 10;
        }}
        .legend-card {{
            position: absolute; bottom: 25px; right: 25px;
            background: rgba(255, 255, 255, 0.90);
            border: 1px solid black; padding: 10px 14px;
            font-family: "Times New Roman", Times, serif; font-size: 10px; color: black;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15); min-width: 155px; z-index: 10;
        }}
        .legend-title {{ font-size: 12px; font-weight: bold; margin-bottom: 6px; font-family: "Times New Roman", Times, serif; color: black; }}
        .legend-item {{ display: flex; align-items: center; margin-bottom: 4px; font-family: "Times New Roman", Times, serif; font-size: 10px; color: black; }}
        .legend-item:last-child {{ margin-bottom: 0; }}
        .legend-line {{ width: 22px; height: 3px; margin-right: 8px; flex-shrink: 0; border-radius: 1px; }}
    </style>
</head>
<body>
<div class="north-arrow"><b>N</b><br>↑</div>
<div id="map"></div>
<div class="legend-card">
    <div class="legend-title"><b>Legend</b></div>
    <div class="legend-item">
        <div class="legend-line" style="background: #27ae60; height: 3.5px;"></div>
        <span>Existing Cycleway</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #fed976;"></div>
        <span>{q0} – {q1} trips</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #feb24c;"></div>
        <span>{q1 + 1} – {q2} trips</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #fd8d3c;"></div>
        <span>{q2 + 1} – {q3} trips</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #f03b20;"></div>
        <span>{q3 + 1} – {q4} trips</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #bd0026; height: 4px;"></div>
        <span>{q4 + 1} – {q5}+ trips</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #e67e22; height: 3.5px; border-top: 1px dashed white;"></div>
        <span>Proposed Project</span>
    </div>
</div>

<script>
    {reducer_script}
    {"const protocol = new pmtiles.Protocol(); maplibregl.addProtocol('pmtiles', protocol.tile);" if is_pmtiles else ""}

    const map = new maplibregl.Map({{
        container: 'map',
        style: {{
            version: 8,
            sources: {sources_json},
            layers: {layers_json}
        }},
        bounds: {bounds_json},
        fitBoundsOptions: {{ padding: 40 }}
    }});

    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(new maplibregl.ScaleControl({{ maxWidth: 100, unit: 'metric' }}), 'bottom-left');

    const popup = new maplibregl.Popup({{ closeButton: false, closeOnClick: false, offset: 12 }});
    map.on('mousemove', 'network-base', (e) => {{
        if (e.features && e.features.length > 0) {{
            map.getCanvas().style.cursor = 'pointer';
            const f = e.features[0];
            popup.setLngLat(e.lngLat)
                 .setHTML(CicloMapReducer.selectEdgePopupHtml(f.properties))
                 .addTo(map);
        }}
    }});
    map.on('mouseleave', 'network-base', () => {{
        map.getCanvas().style.cursor = '';
        popup.remove();
    }});
</script>
</body>
</html>
"""
        file_path = os.path.join(self.output_dir, f"{scenario_prefix}_flow.html")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return file_path

    def generate_bikelanes_flow_map(
        self,
        scenario_prefix: str,
        bbox: List[float],
        total_trips: float = 1.0,
        max_flow: float = 1000.0,
        p50_flow: float = 50.0,
        city_key: Optional[str] = None,
        quantiles: Optional[List[float]] = None
    ) -> str:
        """
        Generates a standalone bikelanes_flow.html MapLibre viewer visualizing ONLY active cycleway corridors
        using ADR 0003 synchronized network quantiles and the sequential green palette.
        """
        source_config = self.tile_source.get_network_source(scenario_prefix)
        sources: Dict[str, Any] = {'network_source': source_config}
        is_pmtiles = "pmtiles://" in source_config.get("url", "")

        if quantiles and len(quantiles) >= 6:
            q0, q1, q2, q3, q4, q5 = [int(v) for v in quantiles[:6]]
        else:
            q0 = 0
            q1 = max(1, int(p50_flow))
            q2 = max(q1 + 1, int(p50_flow + (max_flow - p50_flow) * 0.25))
            q3 = max(q2 + 1, int(p50_flow + (max_flow - p50_flow) * 0.55))
            q4 = max(q3 + 1, int(p50_flow + (max_flow - p50_flow) * 0.85))
            q5 = max(q4 + 1, int(max_flow))

        q2 = max(q1 + 1, q2)
        q3 = max(q2 + 1, q3)
        q4 = max(q3 + 1, q4)
        q5 = max(q4 + 1, q5)

        layers: List[Dict[str, Any]] = [
            {'id': 'background', 'type': 'background', 'paint': {'background-color': '#F8F9FA'}}
        ]

        if city_key:
            context_source = self.tile_source.get_context_source(city_key)
            sources['context_source'] = context_source
            if "pmtiles://" in context_source.get("url", ""):
                is_pmtiles = True
            layers.extend(self._get_context_layers())

        layers.append({
            'id': 'network-bikelanes',
            'type': 'line',
            'source': 'network_source',
            'source-layer': 'network',
            'paint': {
                'line-color': [
                    'case',
                    # 1. Cycleway with flow > 0: 5 discrete green quantile steps matching legend
                    [
                        'all',
                        ['any', ['==', ['get', 'highway'], 'cycleway'], ['==', ['get', 'original_highway'], 'cycleway']],
                        ['>', ['to-number', ['get', 'od_flow']], 0]
                    ],
                    [
                        'step', ['to-number', ['get', 'od_flow']],
                        '#c8e6c9',
                        q1, '#81c784',
                        q2, '#4caf50',
                        q3, '#2e7d32',
                        q4, '#1b5e20'
                    ],
                    # 2. Cycleway without flow: soft reference green
                    ['any', ['==', ['get', 'highway'], 'cycleway'], ['==', ['get', 'original_highway'], 'cycleway']],
                    '#b0d5b4',
                    # 3. Non-cycleway background streets: soft gray
                    '#dcdfe3'
                ],
                'line-width': [
                    'interpolate', ['linear'], ['zoom'],
                    8, ['case', ['any', ['==', ['get', 'highway'], 'cycleway'], ['==', ['get', 'original_highway'], 'cycleway']], 1.8, ['in', ['get', 'highway'], ['literal', ['motorway', 'trunk']]], 0.8, 0.3],
                    11, ['case', ['any', ['==', ['get', 'highway'], 'cycleway'], ['==', ['get', 'original_highway'], 'cycleway']], 3.0, ['in', ['get', 'highway'], ['literal', ['motorway', 'trunk']]], 1.4, 0.5],
                    14, ['case', ['any', ['==', ['get', 'highway'], 'cycleway'], ['==', ['get', 'original_highway'], 'cycleway']], 4.5, ['in', ['get', 'highway'], ['literal', ['motorway', 'trunk']]], 2.2, 0.8]
                ],
                'line-opacity': [
                    'case',
                    ['any', ['==', ['get', 'highway'], 'cycleway'], ['==', ['get', 'original_highway'], 'cycleway']], 0.95,
                    0.25
                ]
            }
        })

        bounds_json = json.dumps(bbox)
        sources_json = json.dumps(sources)
        layers_json = json.dumps(layers)
        reducer_script = self._get_reducer_script()

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>+Ciclo: {scenario_prefix} — Cycleways Flow</title>
    <script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
    <link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet" />
    {"<script src='https://unpkg.com/pmtiles@3.0.7/dist/pmtiles.js'></script>" if is_pmtiles else ""}
    <style>
        body {{ margin: 0; padding: 0; background: #dee2e6; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
        .north-arrow {{
            position: absolute; top: 20px; left: 20px;
            background: rgba(255, 255, 255, 0.90);
            border: 1px solid black; border-radius: 2px; padding: 4px 10px;
            font-family: "Times New Roman", Times, serif; font-size: 16px;
            font-weight: bold; text-align: center; color: black; line-height: 1.1;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15); z-index: 10;
        }}
        .legend-card {{
            position: absolute; bottom: 25px; right: 25px;
            background: rgba(255, 255, 255, 0.90);
            border: 1px solid black; padding: 10px 14px;
            font-family: "Times New Roman", Times, serif; font-size: 10px; color: black;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15); min-width: 160px; z-index: 10;
        }}
        .legend-title {{ font-size: 12px; font-weight: bold; margin-bottom: 6px; font-family: "Times New Roman", Times, serif; color: black; }}
        .legend-item {{ display: flex; align-items: center; margin-bottom: 4px; font-family: "Times New Roman", Times, serif; font-size: 10px; color: black; }}
        .legend-item:last-child {{ margin-bottom: 0; }}
        .legend-line {{ width: 22px; height: 3px; margin-right: 8px; flex-shrink: 0; border-radius: 1px; }}
    </style>
</head>
<body>
<div class="north-arrow"><b>N</b><br>↑</div>
<div id="map"></div>
<div class="legend-card">
    <div class="legend-title"><b>Cycleway Flow</b></div>
    <div class="legend-item"><div class="legend-line" style="background: #c8e6c9; height: 3px;"></div><span>{q0} – {q1} trips</span></div>
    <div class="legend-item"><div class="legend-line" style="background: #81c784; height: 3px;"></div><span>{q1 + 1} – {q2} trips</span></div>
    <div class="legend-item"><div class="legend-line" style="background: #4caf50; height: 3px;"></div><span>{q2 + 1} – {q3} trips</span></div>
    <div class="legend-item"><div class="legend-line" style="background: #2e7d32; height: 3px;"></div><span>{q3 + 1} – {q4} trips</span></div>
    <div class="legend-item"><div class="legend-line" style="background: #1b5e20; height: 4px;"></div><span>{q4 + 1} – {q5}+ trips</span></div>
    <div class="legend-item"><div class="legend-line" style="background: #b0d5b4; height: 2px;"></div><span>Cycleway (No Flow)</span></div>
</div>

<script>
    {reducer_script}
    {"const protocol = new pmtiles.Protocol(); maplibregl.addProtocol('pmtiles', protocol.tile);" if is_pmtiles else ""}

    const map = new maplibregl.Map({{
        container: 'map',
        style: {{
            version: 8,
            sources: {sources_json},
            layers: {layers_json}
        }},
        bounds: {bounds_json},
        fitBoundsOptions: {{ padding: 40 }}
    }});

    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(new maplibregl.ScaleControl({{ maxWidth: 100, unit: 'metric' }}), 'bottom-left');

    const popup = new maplibregl.Popup({{ closeButton: false, closeOnClick: false, offset: 12 }});
    map.on('mousemove', 'network-bikelanes', (e) => {{
        if (e.features && e.features.length > 0) {{
            map.getCanvas().style.cursor = 'pointer';
            const f = e.features[0];
            popup.setLngLat(e.lngLat)
                 .setHTML(CicloMapReducer.selectEdgePopupHtml(f.properties))
                 .addTo(map);
        }}
    }});
    map.on('mouseleave', 'network-bikelanes', () => {{
        map.getCanvas().style.cursor = '';
        popup.remove();
    }});
</script>
</body>
</html>
"""
        file_path = os.path.join(self.output_dir, f"{scenario_prefix}_bikelanes_flow.html")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return file_path

    def generate_project_performance_map(
        self,
        scenario_prefix: str,
        bbox: List[float],
        total_trips: float = 1.0,
        max_flow: float = 1000.0,
        p50_flow: float = 50.0,
        city_key: Optional[str] = None,
        quantiles: Optional[List[float]] = None
    ) -> str:
        """
        Generates a standalone performance.html MapLibre viewer visualizing project corridor capture (PCR %)
        and segment load usage tiers (Local Use to Strategic Artery) with light blue existing cycleways.
        """
        source_config = self.tile_source.get_network_source(scenario_prefix)
        sources: Dict[str, Any] = {'network_source': source_config}
        is_pmtiles = "pmtiles://" in source_config.get("url", "")

        if quantiles and len(quantiles) >= 6:
            q0, q1, q2, q3, q4, q5 = [int(v) for v in quantiles[:6]]
        else:
            q0 = 0
            q1 = max(1, int(p50_flow))
            q2 = max(q1 + 1, int(p50_flow + (max_flow - p50_flow) * 0.25))
            q3 = max(q2 + 1, int(p50_flow + (max_flow - p50_flow) * 0.55))
            q4 = max(q3 + 1, int(p50_flow + (max_flow - p50_flow) * 0.85))
            q5 = max(q4 + 1, int(max_flow))

        q2 = max(q1 + 1, q2)
        q3 = max(q2 + 1, q3)
        q4 = max(q3 + 1, q4)
        q5 = max(q4 + 1, q5)

        layers: List[Dict[str, Any]] = [
            {'id': 'background', 'type': 'background', 'paint': {'background-color': '#F8F9FA'}}
        ]

        if city_key:
            context_source = self.tile_source.get_context_source(city_key)
            sources['context_source'] = context_source
            if "pmtiles://" in context_source.get("url", ""):
                is_pmtiles = True
            layers.extend(self._get_context_layers())

        layers.append({
            'id': 'network-performance',
            'type': 'line',
            'source': 'network_source',
            'source-layer': 'network',
            'paint': {
                'line-color': [
                    'case',
                    ['==', ['get', 'is_project'], True],
                    [
                        'step', ['to-number', ['get', 'od_flow']],
                        '#c8e6c9',
                        q1, '#81c784',
                        q2, '#4caf50',
                        q3, '#2e7d32',
                        q4, '#1b5e20'
                    ],
                    ['any', ['==', ['get', 'highway'], 'cycleway'], ['==', ['get', 'original_highway'], 'cycleway']],
                    '#4fa8e3',
                    '#dcdfe3'
                ],
                'line-width': [
                    'interpolate', ['linear'], ['zoom'],
                    8, ['case', ['==', ['get', 'is_project'], True], 2.2, ['any', ['==', ['get', 'highway'], 'cycleway'], ['==', ['get', 'original_highway'], 'cycleway']], 1.4, 0.3],
                    11, ['case', ['==', ['get', 'is_project'], True], 3.5, ['any', ['==', ['get', 'highway'], 'cycleway'], ['==', ['get', 'original_highway'], 'cycleway']], 2.0, 0.5],
                    14, ['case', ['==', ['get', 'is_project'], True], 5.0, ['any', ['==', ['get', 'highway'], 'cycleway'], ['==', ['get', 'original_highway'], 'cycleway']], 3.0, 0.8]
                ],
                'line-opacity': [
                    'case',
                    ['==', ['get', 'is_project'], True], 1.0,
                    ['any', ['==', ['get', 'highway'], 'cycleway'], ['==', ['get', 'original_highway'], 'cycleway']], 0.85,
                    0.25
                ]
            }
        })

        bounds_json = json.dumps(bbox)
        sources_json = json.dumps(sources)
        layers_json = json.dumps(layers)
        reducer_script = self._get_reducer_script()

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>+Ciclo: {scenario_prefix} — Project Corridor Performance</title>
    <script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
    <link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet" />
    {"<script src='https://unpkg.com/pmtiles@3.0.7/dist/pmtiles.js'></script>" if is_pmtiles else ""}
    <style>
        body {{ margin: 0; padding: 0; background: #dee2e6; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
        .north-arrow {{
            position: absolute; top: 20px; left: 20px;
            background: rgba(255, 255, 255, 0.90);
            border: 1px solid black; border-radius: 2px; padding: 4px 10px;
            font-family: "Times New Roman", Times, serif; font-size: 16px;
            font-weight: bold; text-align: center; color: black; line-height: 1.1;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15); z-index: 10;
        }}
        .legend-card {{
            position: absolute; bottom: 25px; right: 25px;
            background: rgba(255, 255, 255, 0.90);
            border: 1px solid black; padding: 10px 14px;
            font-family: "Times New Roman", Times, serif; font-size: 10px; color: black;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15); min-width: 175px; z-index: 10;
        }}
        .legend-title {{ font-size: 12px; font-weight: bold; margin-bottom: 6px; font-family: "Times New Roman", Times, serif; color: black; }}
        .legend-item {{ display: flex; align-items: center; margin-bottom: 4px; font-family: "Times New Roman", Times, serif; font-size: 10px; color: black; }}
        .legend-item:last-child {{ margin-bottom: 0; }}
        .legend-line {{ width: 22px; height: 3px; margin-right: 8px; flex-shrink: 0; border-radius: 1px; }}
    </style>
</head>
<body>
<div class="north-arrow"><b>N</b><br>↑</div>
<div id="map"></div>
<div class="legend-card">
    <div class="legend-title"><b>Project Performance</b></div>
    <div class="legend-item"><div class="legend-line" style="background: #1b5e20; height: 5px;"></div><span>Strategic Artery (&gt;{q4})</span></div>
    <div class="legend-item"><div class="legend-line" style="background: #2e7d32; height: 4px;"></div><span>Critical Use ({q3 + 1}–{q4})</span></div>
    <div class="legend-item"><div class="legend-line" style="background: #4caf50; height: 3.5px;"></div><span>Trunk Use ({q2 + 1}–{q3})</span></div>
    <div class="legend-item"><div class="legend-line" style="background: #81c784; height: 3px;"></div><span>Connector Use ({q1 + 1}–{q2})</span></div>
    <div class="legend-item"><div class="legend-line" style="background: #c8e6c9; height: 2.5px;"></div><span>Local Use (≤{q1})</span></div>
    <div class="legend-item"><div class="legend-line" style="background: #4fa8e3; height: 2.5px;"></div><span>Existing Cycleway</span></div>
</div>

<script>
    {reducer_script}
    {"const protocol = new pmtiles.Protocol(); maplibregl.addProtocol('pmtiles', protocol.tile);" if is_pmtiles else ""}

    const totalTrips = {total_trips};
    const map = new maplibregl.Map({{
        container: 'map',
        style: {{
            version: 8,
            sources: {sources_json},
            layers: {layers_json}
        }},
        bounds: {bounds_json},
        fitBoundsOptions: {{ padding: 40 }}
    }});

    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(new maplibregl.ScaleControl({{ maxWidth: 100, unit: 'metric' }}), 'bottom-left');

    const popup = new maplibregl.Popup({{ closeButton: false, closeOnClick: false, offset: 12 }});
    map.on('mousemove', 'network-performance', (e) => {{
        if (e.features && e.features.length > 0) {{
            map.getCanvas().style.cursor = 'pointer';
            const f = e.features[0];
            popup.setLngLat(e.lngLat)
                 .setHTML(CicloMapReducer.selectPerformancePopupHtml(f.properties, totalTrips))
                 .addTo(map);
        }}
    }});
    map.on('mouseleave', 'network-performance', () => {{
        map.getCanvas().style.cursor = '';
        popup.remove();
    }});
</script>
</body>
</html>
"""
        file_path = os.path.join(self.output_dir, f"{scenario_prefix}_performance.html")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return file_path

    def generate_h3_purpose_map(
        self,
        scenario_prefix: str,
        bbox: List[float],
        purpose: str = "work",
        column: Optional[str] = None,
        p95: float = 100.0,
        city_key: Optional[str] = None
    ) -> str:
        """
        Generates standalone {scenario}_{purpose}_map.html MapLibre viewers visualizing H3 hexagonal travel demand
        using continuous log-scaled density fills and an embedded purpose switcher dropdown.
        """
        col = column or f"trips_{purpose}"
        h3_source = self.tile_source.get_h3_source(scenario_prefix)
        sources: Dict[str, Any] = {'h3_source': h3_source}
        is_pmtiles = "pmtiles://" in h3_source.get("url", "")

        layers: List[Dict[str, Any]] = [
            {'id': 'background', 'type': 'background', 'paint': {'background-color': '#F8F9FA'}}
        ]

        if city_key:
            context_source = self.tile_source.get_context_source(city_key)
            sources['context_source'] = context_source
            if "pmtiles://" in context_source.get("url", ""):
                is_pmtiles = True
            layers.extend(self._get_context_layers())

        log_p95 = max(0.1, float(import_math := __import__('math').log1p(max(1.0, float(p95)))))

        # Purpose Palettes conforming to academic Plotly
        palettes = {
            "work": ["#e0f7fa", "#80deea", "#26c6da", "#00acc1", "#006064"],
            "study": ["#fffde7", "#fff59d", "#ffee58", "#fdd835", "#f57f17"],
            "shopping": ["#fce4ec", "#f48fb1", "#ec407a", "#d81b60", "#880e4f"],
            "recreational": ["#e8f5e9", "#a5d6a7", "#66bb6a", "#43a047", "#1b5e20"],
            "personal": ["#e0f2f1", "#80cbc4", "#26a69a", "#00897b", "#004d40"],
            "returning_home": ["#ede7f6", "#b39ddb", "#7e57c2", "#5e35b1", "#311b92"],
            "default": ["#fff3e0", "#ffcc80", "#ffa726", "#fb8c00", "#e65100"]
        }
        palette = palettes.get(purpose, palettes["default"])

        layers.append({
            'id': 'h3-hexagons',
            'type': 'fill',
            'source': 'h3_source',
            'source-layer': 'h3',
            'paint': {
                'fill-color': [
                    'interpolate', ['linear'],
                    ['min', 1.0, ['/', ['ln', ['+', 1, ['max', 0, ['get', col]]]], log_p95]],
                    0.00, palette[0],
                    0.25, palette[1],
                    0.50, palette[2],
                    0.75, palette[3],
                    1.00, palette[4]
                ],
                'fill-opacity': [
                    'case',
                    ['<=', ['get', col], 0], 0.0,
                    0.40
                ],
                'fill-outline-color': 'rgba(0,0,0,0.08)'
            }
        })

        bounds_json = json.dumps(bbox)
        sources_json = json.dumps(sources)
        layers_json = json.dumps(layers)
        reducer_script = self._get_reducer_script()
        purpose_title = purpose.replace("_", " ").title()

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>+Ciclo: {scenario_prefix} — {purpose_title} Trips (H3 Density)</title>
    <script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
    <link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet" />
    {"<script src='https://unpkg.com/pmtiles@3.0.7/dist/pmtiles.js'></script>" if is_pmtiles else ""}
    <style>
        body {{ margin: 0; padding: 0; background: #dee2e6; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
        .north-arrow {{
            position: absolute; top: 20px; left: 20px;
            background: rgba(255, 255, 255, 0.90);
            border: 1px solid black; border-radius: 2px; padding: 4px 10px;
            font-family: "Times New Roman", Times, serif; font-size: 16px;
            font-weight: bold; text-align: center; color: black; line-height: 1.1;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15); z-index: 10;
        }}
        .legend-card {{
            position: absolute; bottom: 25px; right: 25px;
            background: rgba(255, 255, 255, 0.90);
            border: 1px solid black; padding: 10px 14px;
            font-family: "Times New Roman", Times, serif; font-size: 10px; color: black;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15); min-width: 175px; z-index: 10;
        }}
        .legend-title {{ font-size: 12px; font-weight: bold; margin-bottom: 6px; font-family: "Times New Roman", Times, serif; color: black; }}
        .legend-item {{ display: flex; align-items: center; margin-bottom: 4px; font-family: "Times New Roman", Times, serif; font-size: 10px; color: black; }}
        .legend-item:last-child {{ margin-bottom: 0; }}
        .legend-swatch {{ width: 20px; height: 12px; margin-right: 8px; flex-shrink: 0; border: 1px solid rgba(0,0,0,0.15); }}
        .purpose-selector {{
            position: absolute; top: 20px; right: 60px; z-index: 10;
            background: rgba(255, 255, 255, 0.94); border: 1px solid black;
            padding: 6px 10px; font-family: "Times New Roman", Times, serif; font-size: 12px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.15);
        }}
        .purpose-selector select {{
            font-family: inherit; font-size: inherit; background: transparent; border: none; outline: none; cursor: pointer;
        }}
    </style>
</head>
<body>
<div class="north-arrow"><b>N</b><br>↑</div>
<div class="purpose-selector">
    <label><b>Trip Purpose: </b></label>
    <select id="purpose-select">
        <option value="work" {"selected" if purpose == "work" else ""}>Work Commute</option>
        <option value="study" {"selected" if purpose == "study" else ""}>Study</option>
        <option value="shopping" {"selected" if purpose == "shopping" else ""}>Shopping</option>
        <option value="recreational" {"selected" if purpose == "recreational" else ""}>Recreational</option>
        <option value="personal" {"selected" if purpose == "personal" else ""}>Personal Errands</option>
        <option value="returning_home" {"selected" if purpose == "returning_home" else ""}>Return Home</option>
    </select>
</div>
<div id="map"></div>
<div class="legend-card">
    <div class="legend-title" id="legend-title"><b>{purpose_title} Trips (Density)</b></div>
    <div class="legend-item"><div class="legend-swatch" style="background: {palette[4]};"></div><span>High Density (&gt;{int(p95 * 0.75)})</span></div>
    <div class="legend-item"><div class="legend-swatch" style="background: {palette[3]};"></div><span>Upper Medium ({int(p95 * 0.40)}–{int(p95 * 0.75)})</span></div>
    <div class="legend-item"><div class="legend-swatch" style="background: {palette[2]};"></div><span>Medium Density ({int(p95 * 0.15)}–{int(p95 * 0.40)})</span></div>
    <div class="legend-item"><div class="legend-swatch" style="background: {palette[1]};"></div><span>Low Density (1–{int(p95 * 0.15)})</span></div>
    <div class="legend-item"><div class="legend-swatch" style="background: {palette[0]};"></div><span>Minimal (0–1 trips)</span></div>
</div>

<script>
    {reducer_script}
    {"const protocol = new pmtiles.Protocol(); maplibregl.addProtocol('pmtiles', protocol.tile);" if is_pmtiles else ""}

    let currentPurpose = "{purpose}";
    const logP95 = {log_p95};
    const palettes = {json.dumps(palettes)};

    const map = new maplibregl.Map({{
        container: 'map',
        style: {{
            version: 8,
            sources: {sources_json},
            layers: {layers_json}
        }},
        bounds: {bounds_json},
        fitBoundsOptions: {{ padding: 40 }}
    }});

    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(new maplibregl.ScaleControl({{ maxWidth: 100, unit: 'metric' }}), 'bottom-left');

    const popup = new maplibregl.Popup({{ closeButton: false, closeOnClick: false, offset: 12 }});
    map.on('mousemove', 'h3-hexagons', (e) => {{
        if (e.features && e.features.length > 0) {{
            map.getCanvas().style.cursor = 'pointer';
            const f = e.features[0];
            popup.setLngLat(e.lngLat)
                 .setHTML(CicloMapReducer.selectH3PopupHtml(f.properties, currentPurpose))
                 .addTo(map);
        }}
    }});
    map.on('mouseleave', 'h3-hexagons', () => {{
        map.getCanvas().style.cursor = '';
        popup.remove();
    }});

    // Dynamic Purpose Switcher
    document.getElementById('purpose-select').addEventListener('change', (e) => {{
        const newPurpose = e.target.value;
        currentPurpose = newPurpose;
        const col = 'trips_' + newPurpose;
        const pal = palettes[newPurpose] || palettes.default;
        
        map.setPaintProperty('h3-hexagons', 'fill-color', [
            'interpolate', ['linear'],
            ['min', 1.0, ['/', ['ln', ['+', 1, ['max', 0, ['get', col]]]], logP95]],
            0.00, pal[0],
            0.25, pal[1],
            0.50, pal[2],
            0.75, pal[3],
            1.00, pal[4]
        ]);
        document.getElementById('legend-title').innerHTML = '<b>' + newPurpose.replace('_', ' ').toUpperCase() + ' Trips (Density)</b>';
    }});
</script>
</body>
</html>
"""
        file_path = os.path.join(self.output_dir, f"{scenario_prefix}_{purpose}_map.html")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return file_path

    def generate_delta_map(
        self,
        scenario_prefix: str,
        bbox: List[float],
        max_delta: float = 500.0,
        city_key: Optional[str] = None
    ) -> str:
        """
        Generates a standalone delta.html MapLibre viewer visualizing flow differential (ΔF).
        Blue indicates induced cycle flow; red indicates flow reduction/cannibalization.
        """
        delta_source = self.tile_source.get_delta_source(scenario_prefix)
        network_source = self.tile_source.get_network_source(scenario_prefix)
        sources: Dict[str, Any] = {
            'network_source': network_source,
            'delta_source': delta_source
        }
        is_pmtiles = "pmtiles://" in delta_source.get("url", "") or "pmtiles://" in network_source.get("url", "")

        layers: List[Dict[str, Any]] = [
            {
                'id': 'background',
                'type': 'background',
                'paint': {'background-color': '#F8F9FA'}
            }
        ]

        if city_key:
            context_source = self.tile_source.get_context_source(city_key)
            sources['context_source'] = context_source
            if "pmtiles://" in context_source.get("url", ""):
                is_pmtiles = True
            layers.extend(self._get_context_layers())

        layers.append({
            'id': 'network-base',
            'type': 'line',
            'source': 'network_source',
            'source-layer': 'network',
            'paint': {
                'line-color': [
                    'case',
                    ['==', ['get', 'highway'], 'cycleway'], '#27ae60',
                    [
                        'match', ['get', 'highway'],
                        'motorway', '#666666',
                        'trunk', '#888888',
                        'primary', '#888888',
                        'secondary', '#A0A0A0',
                        'tertiary', '#A0A0A0',
                        'residential', '#C8C8C8',
                        'living_street', '#C8C8C8',
                        '#D0D0D0'
                    ]
                ],
                'line-width': [
                    'interpolate', ['linear'], ['zoom'],
                    8, ['case', ['==', ['get', 'highway'], 'cycleway'], 1.2, ['in', ['get', 'highway'], ['literal', ['motorway', 'trunk']]], 0.8, 0.4],
                    11, ['case', ['==', ['get', 'highway'], 'cycleway'], 2.0, ['in', ['get', 'highway'], ['literal', ['motorway', 'trunk']]], 1.4, 0.6],
                    14, ['case', ['==', ['get', 'highway'], 'cycleway'], 3.2, ['in', ['get', 'highway'], ['literal', ['motorway', 'trunk']]], 2.2, 0.9]
                ],
                'line-opacity': 0.60
            }
        })

        layers.append({
            'id': 'delta-lines',
            'type': 'line',
            'source': 'delta_source',
            'source-layer': 'delta',
            'filter': ['!=', ['get', 'delta_flow'], 0],
            'paint': {
                'line-color': [
                    'interpolate', ['linear'], ['get', 'delta_flow'],
                    -max_delta, '#b2182b',
                    -max_delta * 0.70, '#d6604d',
                    -max_delta * 0.40, '#f4a582',
                    -max_delta * 0.15, '#fddbc7',
                    0, 'rgba(0,0,0,0)',
                    max_delta * 0.15, '#d1e5f0',
                    max_delta * 0.40, '#92c5de',
                    max_delta * 0.70, '#4393c3',
                    max_delta, '#2166ac'
                ],
                'line-width': [
                    'interpolate', ['linear'], ['zoom'],
                    8, ['+', 0.6, ['*', ['min', 1.0, ['/', ['abs', ['get', 'delta_flow']], max_delta]], 1.8]],
                    11, ['+', 0.9, ['*', ['min', 1.0, ['/', ['abs', ['get', 'delta_flow']], max_delta]], 3.5]],
                    14, ['+', 1.5, ['*', ['min', 1.0, ['/', ['abs', ['get', 'delta_flow']], max_delta]], 5.5]]
                ],
                'line-opacity': 0.95
            }
        })

        bounds_json = json.dumps(bbox)
        sources_json = json.dumps(sources)
        layers_json = json.dumps(layers)
        reducer_script = self._get_reducer_script()

        d_crit = int(max_delta)
        d_maj = max(1, int(max_delta * 0.70))
        d_med = max(1, int(max_delta * 0.40))
        d_light = max(1, int(max_delta * 0.15))

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>+Ciclo: {scenario_prefix} — Delta Flow (ΔF)</title>
    <script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
    <link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet" />
    {"<script src='https://unpkg.com/pmtiles@3.0.7/dist/pmtiles.js'></script>" if is_pmtiles else ""}
    <style>
        body {{ margin: 0; padding: 0; background: #dee2e6; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
        .north-arrow {{
            position: absolute; top: 20px; left: 20px;
            background: rgba(255, 255, 255, 0.90);
            border: 1px solid black; border-radius: 2px; padding: 4px 10px;
            font-family: "Times New Roman", Times, serif; font-size: 16px;
            font-weight: bold; text-align: center; color: black; line-height: 1.1;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15); z-index: 10;
        }}
        .legend-card {{
            position: absolute; bottom: 25px; right: 25px;
            background: rgba(255, 255, 255, 0.90);
            border: 1px solid black; padding: 10px 14px;
            font-family: "Times New Roman", Times, serif; font-size: 10px; color: black;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15); min-width: 190px; z-index: 10;
        }}
        .legend-title {{ font-size: 12px; font-weight: bold; margin-bottom: 6px; font-family: "Times New Roman", Times, serif; color: black; }}
        .legend-item {{ display: flex; align-items: center; margin-bottom: 4px; font-family: "Times New Roman", Times, serif; font-size: 10px; color: black; }}
        .legend-item:last-child {{ margin-bottom: 0; }}
        .legend-line {{ width: 22px; height: 3px; margin-right: 8px; flex-shrink: 0; border-radius: 1px; }}
    </style>
</head>
<body>
<div class="north-arrow"><b>N</b><br>↑</div>
<div id="map"></div>
<div class="legend-card">
    <div class="legend-title"><b>Legend</b></div>
    <div class="legend-item">
        <div class="legend-line" style="background: #2166ac; height: 4px;"></div>
        <span>Critical Peak Increase (+{d_maj + 1} to +{d_crit})</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #4393c3;"></div>
        <span>Major Increase (+{d_med + 1} to +{d_maj})</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #92c5de;"></div>
        <span>Medium Increase (+{d_light + 1} to +{d_med})</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #d1e5f0;"></div>
        <span>Light Increase (+1 to +{d_light})</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #CCCCCC;"></div>
        <span>No Change (0)</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #fddbc7;"></div>
        <span>Light Reduction (-{d_light} to -1)</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #f4a582;"></div>
        <span>Medium Reduction (-{d_med} to -{d_light + 1})</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #d6604d;"></div>
        <span>Major Reduction (-{d_maj} to -{d_med + 1})</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #b2182b; height: 4px;"></div>
        <span>Critical Reduction (-{d_crit} to -{d_maj + 1})</span>
    </div>
</div>

<script>
    {reducer_script}
    {"const protocol = new pmtiles.Protocol(); maplibregl.addProtocol('pmtiles', protocol.tile);" if is_pmtiles else ""}

    const map = new maplibregl.Map({{
        container: 'map',
        style: {{
            version: 8,
            sources: {sources_json},
            layers: {layers_json}
        }},
        bounds: {bounds_json},
        fitBoundsOptions: {{ padding: 40 }}
    }});

    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(new maplibregl.ScaleControl({{ maxWidth: 100, unit: 'metric' }}), 'bottom-left');

    const popup = new maplibregl.Popup({{ closeButton: false, closeOnClick: false, offset: 12 }});
    map.on('mousemove', 'delta-lines', (e) => {{
        if (e.features && e.features.length > 0) {{
            map.getCanvas().style.cursor = 'pointer';
            const f = e.features[0];
            popup.setLngLat(e.lngLat)
                 .setHTML(CicloMapReducer.selectDeltaPopupHtml(f.properties))
                 .addTo(map);
        }}
    }});
    map.on('mouseleave', 'delta-lines', () => {{
        map.getCanvas().style.cursor = '';
        popup.remove();
    }});
</script>
</body>
</html>
"""
        file_path = os.path.join(self.output_dir, f"{scenario_prefix}_delta.html")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return file_path

    def generate_compare_map(
        self,
        scenario_prefix: str,
        reference_scenario_prefix: str,
        bbox: List[float],
        city_key: Optional[str] = None,
        max_flow: float = 1000.0,
        p50_flow: float = 50.0,
        quantiles: Optional[List[float]] = None
    ) -> str:
        """
        Generates a split-screen swipe comparison viewer (compare.html)
        comparing baseline flow (left) against project scenario flow (right).
        """
        ref_source = self.tile_source.get_network_source(reference_scenario_prefix)
        cur_source = self.tile_source.get_network_source(scenario_prefix)
        is_pmtiles = "pmtiles://" in ref_source.get("url", "") or "pmtiles://" in cur_source.get("url", "")

        if quantiles and len(quantiles) >= 6:
            q0, q1, q2, q3, q4, q5 = [int(v) for v in quantiles[:6]]
        else:
            q0 = 0
            q1 = max(1, int(p50_flow))
            q2 = max(q1 + 1, int(p50_flow + (max_flow - p50_flow) * 0.25))
            q3 = max(q2 + 1, int(p50_flow + (max_flow - p50_flow) * 0.55))
            q4 = max(q3 + 1, int(p50_flow + (max_flow - p50_flow) * 0.85))
            q5 = max(q4 + 1, int(max_flow))

        q2 = max(q1 + 1, q2)
        q3 = max(q2 + 1, q3)
        q4 = max(q3 + 1, q4)
        q5 = max(q4 + 1, q5)

        before_sources: Dict[str, Any] = {'before_tiles': ref_source}
        after_sources: Dict[str, Any] = {'after_tiles': cur_source}

        before_layers: List[Dict[str, Any]] = [
            {'id': 'bg', 'type': 'background', 'paint': {'background-color': '#F8F9FA'}}
        ]
        after_layers: List[Dict[str, Any]] = [
            {'id': 'bg', 'type': 'background', 'paint': {'background-color': '#F8F9FA'}}
        ]

        if city_key:
            context_source = self.tile_source.get_context_source(city_key)
            before_sources['context_source'] = context_source
            after_sources['context_source'] = context_source
            if "pmtiles://" in context_source.get("url", ""):
                is_pmtiles = True
            before_layers.extend(self._get_context_layers())
            after_layers.extend(self._get_context_layers())

        flow_line_paint = self._get_flow_line_paint(q1, q2, q3, q4, q5, max_flow)
        before_layers.append({
            'id': 'lines', 'type': 'line', 'source': 'before_tiles', 'source-layer': 'network',
            'paint': flow_line_paint
        })
        after_layers.append({
            'id': 'lines', 'type': 'line', 'source': 'after_tiles', 'source-layer': 'network',
            'paint': flow_line_paint
        })

        bounds_json = json.dumps(bbox)
        before_sources_json = json.dumps(before_sources)
        after_sources_json = json.dumps(after_sources)
        before_layers_json = json.dumps(before_layers)
        after_layers_json = json.dumps(after_layers)
        reducer_script = self._get_reducer_script()

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>+Ciclo: {scenario_prefix} vs {reference_scenario_prefix} — Comparison</title>
    <script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
    <link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet" />
    {"<script src='https://unpkg.com/pmtiles@3.0.7/dist/pmtiles.js'></script>" if is_pmtiles else ""}
    <style>
        body {{ margin: 0; padding: 0; overflow: hidden; background: #dee2e6; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
        .map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
        #slider-container {{
            position: absolute; top: 0; bottom: 0; left: 50%; width: 4px;
            background: #212529; cursor: ew-resize; z-index: 20;
            box-shadow: 0 0 12px rgba(0,0,0,0.3);
        }}
        #slider-handle {{
            position: absolute; top: 50%; left: -16px; width: 36px; height: 36px;
            background: #ffffff; border: 2px solid #212529; border-radius: 50%; cursor: ew-resize;
            box-shadow: 0 4px 12px rgba(0,0,0,0.25);
            display: flex; align-items: center; justify-content: center;
            font-size: 14px; color: #212529; font-weight: bold;
        }}
        .badge {{
            position: absolute; top: 20px; z-index: 10;
            background: rgba(255, 255, 255, 0.94); backdrop-filter: blur(8px);
            border: 1px solid rgba(0, 0, 0, 0.12);
            color: #212529; padding: 8px 14px; border-radius: 6px;
            font-size: 13px; font-weight: 600;
            box-shadow: 0 4px 16px rgba(0,0,0,0.08);
        }}
        #badge-before {{ left: 20px; }}
        #badge-after {{ right: 20px; }}
        .north-arrow {{
            position: absolute; top: 20px; left: 50%; transform: translateX(-50%);
            background: rgba(255, 255, 255, 0.90);
            border: 1px solid black; border-radius: 2px; padding: 4px 10px;
            font-family: "Times New Roman", Times, serif; font-size: 16px;
            font-weight: bold; text-align: center; color: black; line-height: 1.1;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15); z-index: 30;
        }}
        .legend-card {{
            position: absolute; bottom: 25px; right: 25px;
            background: rgba(255, 255, 255, 0.90);
            border: 1px solid black; padding: 10px 14px;
            font-family: "Times New Roman", Times, serif; font-size: 10px; color: black;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15); min-width: 155px; z-index: 30;
        }}
        .legend-title {{ font-size: 12px; font-weight: bold; margin-bottom: 6px; font-family: "Times New Roman", Times, serif; color: black; }}
        .legend-item {{ display: flex; align-items: center; margin-bottom: 4px; font-family: "Times New Roman", Times, serif; font-size: 10px; color: black; }}
        .legend-item:last-child {{ margin-bottom: 0; }}
        .legend-line {{ width: 22px; height: 3px; margin-right: 8px; flex-shrink: 0; border-radius: 1px; }}
    </style>
</head>
<body>
<div id="before-map" class="map"></div>
<div id="after-map" class="map"></div>
<div id="slider-container"><div id="slider-handle">↔</div></div>
<div id="badge-before" class="badge">Baseline: {reference_scenario_prefix}</div>
<div id="badge-after" class="badge">Project: {scenario_prefix}</div>
<div class="north-arrow"><b>N</b><br>↑</div>
<div class="legend-card">
    <div class="legend-title"><b>Legend</b></div>
    <div class="legend-item"><div class="legend-line" style="background: #27ae60; height: 3.5px;"></div><span>Existing Cycleway</span></div>
    <div class="legend-item"><div class="legend-line" style="background: #fed976;"></div><span>Low Flow</span></div>
    <div class="legend-item"><div class="legend-line" style="background: #feb24c;"></div><span>Moderate Flow</span></div>
    <div class="legend-item"><div class="legend-line" style="background: #fd8d3c;"></div><span>Medium Flow</span></div>
    <div class="legend-item"><div class="legend-line" style="background: #f03b20;"></div><span>High Flow</span></div>
    <div class="legend-item"><div class="legend-line" style="background: #bd0026; height: 4px;"></div><span>Peak Flow</span></div>
</div>

<script>
    {reducer_script}
    {"const protocol = new pmtiles.Protocol(); maplibregl.addProtocol('pmtiles', protocol.tile);" if is_pmtiles else ""}

    const beforeMap = new maplibregl.Map({{
        container: 'before-map',
        style: {{
            version: 8,
            sources: {before_sources_json},
            layers: {before_layers_json}
        }},
        bounds: {bounds_json}, fitBoundsOptions: {{ padding: 30 }}
    }});

    const afterMap = new maplibregl.Map({{
        container: 'after-map',
        style: {{
            version: 8,
            sources: {after_sources_json},
            layers: {after_layers_json}
        }},
        bounds: {bounds_json}, fitBoundsOptions: {{ padding: 30 }}
    }});

    // Synchronize cameras
    let isSyncing = false;
    function sync(source, target) {{
        source.on('move', () => {{
            if (!isSyncing) {{
                isSyncing = true;
                target.jumpTo({{ center: source.getCenter(), zoom: source.getZoom(), bearing: source.getBearing(), pitch: source.getPitch() }});
                isSyncing = false;
            }}
        }});
    }}
    sync(beforeMap, afterMap);
    sync(afterMap, beforeMap);

    // Interactive Swipe Divider
    const slider = document.getElementById('slider-container');
    const afterContainer = document.getElementById('after-map');
    let isDragging = false;

    function setSliderPosition(x) {{
        const width = window.innerWidth;
        const clampedX = Math.max(0, Math.min(x, width));
        slider.style.left = clampedX + 'px';
        afterContainer.style.clipPath = `polygon(${{clampedX}}px 0%, 100% 0%, 100% 100%, ${{clampedX}}px 100%)`;
    }}

    setSliderPosition(window.innerWidth / 2);

    slider.addEventListener('mousedown', () => {{ isDragging = true; }});
    window.addEventListener('mouseup', () => {{ isDragging = false; }});
    window.addEventListener('mousemove', (e) => {{
        if (isDragging) setSliderPosition(e.clientX);
    }});
</script>
</body>
</html>
"""
        file_path = os.path.join(self.output_dir, f"{scenario_prefix}_compare.html")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return file_path

    def generate_impedance_map(
        self,
        scenario_prefix: str,
        city_key: str,
        bbox: List[float],
        imp_weights: Optional[Dict[str, float]] = None
    ) -> str:
        """
        Generates an impedance.html MapLibre viewer visualizing road hierarchy traversal costs
        and cycling suitability impedance multipliers overlaid on local context vectors.
        """
        weights = imp_weights or {
            "primary": 15.0,
            "secondary": 7.0,
            "tertiary": 3.0,
            "local": 1.5,
            "bike": 0.5
        }
        source_config = self.tile_source.get_network_source(scenario_prefix)
        context_config = self.tile_source.get_context_source(city_key)
        is_pmtiles = "pmtiles://" in source_config.get("url", "") or "pmtiles://" in context_config.get("url", "")
        bounds_json = json.dumps(bbox)

        sources = {
            'network_source': source_config,
            'context_source': context_config
        }
        layers: List[Dict[str, Any]] = [
            {
                'id': 'bg',
                'type': 'background',
                'paint': {'background-color': '#F8F9FA'}
            }
        ]
        layers.extend(self._get_context_layers())
        layers.append({
            'id': 'road-hierarchy',
            'type': 'line',
            'source': 'network_source',
            'source-layer': 'network',
            'paint': {
                'line-color': [
                    'match', ['get', 'highway'],
                    'cycleway', '#27ae60',
                    'project_new', '#e67e22',
                    'residential', '#2196f3',
                    'living_street', '#2196f3',
                    'unclassified', '#2196f3',
                    'service', '#607d8b',
                    'tertiary', '#9c27b0',
                    'secondary', '#ff9800',
                    'primary', '#e91e63',
                    'trunk', '#e91e63',
                    'motorway', '#e91e63',
                    '#9e9e9e'
                ],
                'line-width': [
                    'interpolate', ['linear'], ['zoom'],
                    8, ['match', ['get', 'highway'], 'cycleway', 1.4, 'project_new', 1.6, 'primary', 1.2, 'secondary', 0.9, 'tertiary', 0.7, 'residential', 0.5, 0.4],
                    11, ['match', ['get', 'highway'], 'cycleway', 2.2, 'project_new', 2.8, 'primary', 1.8, 'secondary', 1.4, 'tertiary', 1.1, 'residential', 0.8, 0.6],
                    14, ['match', ['get', 'highway'], 'cycleway', 3.5, 'project_new', 4.2, 'primary', 2.8, 'secondary', 2.2, 'tertiary', 1.8, 'residential', 1.4, 0.9]
                ],
                'line-opacity': 0.85
            }
        })

        sources_json = json.dumps(sources)
        layers_json = json.dumps(layers)
        reducer_script = self._get_reducer_script()

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>+Ciclo: {scenario_prefix} — Road Typology & Impedance</title>
    <script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
    <link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet" />
    {"<script src='https://unpkg.com/pmtiles@3.0.7/dist/pmtiles.js'></script>" if is_pmtiles else ""}
    <style>
        body {{ margin: 0; padding: 0; background: #dee2e6; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
        .north-arrow {{
            position: absolute; top: 20px; left: 20px;
            background: rgba(255, 255, 255, 0.90);
            border: 1px solid black; border-radius: 2px; padding: 4px 10px;
            font-family: "Times New Roman", Times, serif; font-size: 16px;
            font-weight: bold; text-align: center; color: black; line-height: 1.1;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15); z-index: 10;
        }}
        .legend-card {{
            position: absolute; bottom: 25px; right: 25px;
            background: rgba(255, 255, 255, 0.90);
            border: 1px solid black; padding: 10px 14px;
            font-family: "Times New Roman", Times, serif; font-size: 10px; color: black;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15); min-width: 155px; z-index: 10;
        }}
        .legend-title {{ font-size: 12px; font-weight: bold; margin-bottom: 6px; font-family: "Times New Roman", Times, serif; color: black; }}
        .legend-item {{ display: flex; align-items: center; margin-bottom: 4px; font-family: "Times New Roman", Times, serif; font-size: 10px; color: black; }}
        .legend-item:last-child {{ margin-bottom: 0; }}
        .legend-line {{ width: 22px; height: 3px; margin-right: 8px; flex-shrink: 0; border-radius: 1px; }}
    </style>
</head>
<body>
<div class="north-arrow"><b>N</b><br>↑</div>
<div id="map"></div>
<div class="legend-card">
    <div class="legend-title"><b>Legend</b></div>
    <div class="legend-item">
        <div class="legend-line" style="background: #27ae60; height: 3.5px;"></div>
        <span>Existing Cycleway</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #e67e22; height: 3.5px;"></div>
        <span>New Project (+Ciclo)</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #2196f3;"></div>
        <span>Residential Street</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #9c27b0;"></div>
        <span>Tertiary Road</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #ff9800;"></div>
        <span>Secondary Road</span>
    </div>
    <div class="legend-item">
        <div class="legend-line" style="background: #e91e63;"></div>
        <span>Primary Road</span>
    </div>
</div>

<script>
    {reducer_script}
    {"const protocol = new pmtiles.Protocol(); maplibregl.addProtocol('pmtiles', protocol.tile);" if is_pmtiles else ""}

    const map = new maplibregl.Map({{
        container: 'map',
        style: {{
            version: 8,
            sources: {sources_json},
            layers: {layers_json}
        }},
        bounds: {bounds_json},
        fitBoundsOptions: {{ padding: 40 }}
    }});

    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(new maplibregl.ScaleControl({{ maxWidth: 100, unit: 'metric' }}), 'bottom-left');

    const popup = new maplibregl.Popup({{ closeButton: false, closeOnClick: false, offset: 12 }});
    map.on('mousemove', 'road-hierarchy', (e) => {{
        if (e.features && e.features.length > 0) {{
            map.getCanvas().style.cursor = 'pointer';
            const f = e.features[0];
            popup.setLngLat(e.lngLat)
                 .setHTML(CicloMapReducer.selectEdgePopupHtml(f.properties))
                 .addTo(map);
        }}
    }});
    map.on('mouseleave', 'road-hierarchy', () => {{
        map.getCanvas().style.cursor = '';
        popup.remove();
    }});
</script>
</body>
</html>
"""
        file_path = os.path.join(self.output_dir, f"{scenario_prefix}_impedance.html")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return file_path
