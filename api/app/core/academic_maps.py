import geopandas as gpd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import os
import json
import geojson
from shapely.geometry import Polygon, MultiPolygon, LineString
import osmnx as ox

class AcademicMapGenerator:
    '''
    Module to generate publication-ready maps for urban network analysis using Plotly.
    Standards: Fixed Portrait (570x800), Centered HTML, Black Frame, Strict Visual Pruning.
    '''
    def __init__(self, output_dir="data/maps"):
        self.output_dir = output_dir
        self.context_dir = "data/map_layers"
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.context_dir, exist_ok=True)

    def _ensure_context_layers(self, city_name, bbox, srid):
        '''
        Downloads Forest Areas, Water Bodies (including Bay/Sea), Buildings and Urban Limit from OSM.
        '''
        green_path = os.path.join(self.context_dir, f"{city_name}_forests.geojson")
        water_path = os.path.join(self.context_dir, f"{city_name}_water.geojson")
        build_path = os.path.join(self.context_dir, f"{city_name}_buildings.geojson")
        limit_path = os.path.join(self.context_dir, f"{city_name}_urban_limit.geojson")
        
        green_gdf = gpd.GeoDataFrame()
        water_gdf = gpd.GeoDataFrame()
        build_gdf = gpd.GeoDataFrame()
        limit_gdf = gpd.GeoDataFrame()

        from pyproj import Transformer
        transformer = Transformer.from_crs(f"EPSG:{srid}", "EPSG:4326", always_xy=True)
        west_m, south_m, east_m, north_m = bbox
        span_x, span_y = east_m - west_m, north_m - south_m
        # Expand context BBOX to capture the Bay
        west_e, east_e = west_m - (span_x * 0.4), east_m + (span_x * 0.4)
        south_e, north_e = south_m - (span_y * 0.4), north_m + (span_y * 0.4)
        lon_min, lat_min = transformer.transform(west_e, south_e)
        lon_max, lat_max = transformer.transform(east_e, north_e)
        
        if not os.path.exists(green_path):
            try:
                tags = {'landuse': 'forest', 'natural': 'wood'}
                green_gdf = ox.geometries_from_bbox(lat_max, lat_min, lon_max, lon_min, tags=tags)
                green_gdf = green_gdf[green_gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])]
                if not green_gdf.empty:
                    green_gdf = green_gdf[['geometry']].to_crs(epsg=srid)
                    green_gdf.to_file(green_path, driver='GeoJSON')
                else: gpd.GeoDataFrame(geometry=[]).to_file(green_path, driver='GeoJSON')
            except Exception: pass
        else: green_gdf = gpd.read_file(green_path)

        if not os.path.exists(water_path):
            try:
                tags = {
                    'natural': ['water', 'bay', 'strait', 'coastline', 'wetland'], 
                    'water': ['river', 'lake', 'sea', 'oxbow', 'bay', 'basin'], 
                    'waterway': ['riverbank', 'dock', 'canal']
                }
                water_gdf = ox.geometries_from_bbox(lat_max, lat_min, lon_max, lon_min, tags=tags)
                water_gdf = water_gdf[water_gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])]
                if not water_gdf.empty:
                    water_gdf = water_gdf[['geometry']].to_crs(epsg=srid)
                    water_gdf.to_file(water_path, driver='GeoJSON')
                else: gpd.GeoDataFrame(geometry=[]).to_file(water_path, driver='GeoJSON')
            except Exception: pass
        else: water_gdf = gpd.read_file(water_path)

        if not os.path.exists(build_path):
            try:
                area = (lon_max - lon_min) * (lat_max - lat_min)
                if area > 0.05:
                    print(f"   - [OSM] Bounding box area {area:.4f} is too large for building download. Skipping buildings to prevent OOM.")
                    gpd.GeoDataFrame(geometry=[]).to_file(build_path, driver='GeoJSON')
                else:
                    tags = {'building': True, 'landuse': ['residential', 'commercial', 'industrial', 'retail']}
                    build_gdf = ox.geometries_from_bbox(lat_max, lat_min, lon_max, lon_min, tags=tags)
                    build_gdf = build_gdf[build_gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])]
                    if not build_gdf.empty:
                        build_gdf = build_gdf[['geometry']].to_crs(epsg=srid)
                        build_gdf.to_file(build_path, driver='GeoJSON')
                    else: gpd.GeoDataFrame(geometry=[]).to_file(build_path, driver='GeoJSON')
            except Exception: pass
        else: build_gdf = gpd.read_file(build_path)

        if not os.path.exists(limit_path):
            try:
                limit_gdf = ox.geometries_from_bbox(lat_max, lat_min, lon_max, lon_min, tags={'boundary': 'administrative', 'admin_level': '8'})
                if not limit_gdf.empty:
                    limit_gdf = limit_gdf[['geometry']].to_crs(epsg=srid)
                    limit_gdf.to_file(limit_path, driver='GeoJSON')
            except Exception: pass
        else: limit_gdf = gpd.read_file(limit_path)
            
        return green_gdf, water_gdf, build_gdf, limit_gdf

    def _apply_academic_layout(self, fig, title, x_range=None, y_range=None, width=570, height=800, show_stats=None, bg_color="#F4F3F0"):
        # Force title off the canvas for all maps per user footnote preferences
        title = None
        top_margin = 30
        
        fig.update_layout(
            width=width, height=height,
            title=None,
            margin=dict(l=30, r=30, t=top_margin, b=30),
            paper_bgcolor="#F1F3F0", plot_bgcolor=bg_color,
            showlegend=True,
            legend=dict(title=dict(text="<b>Legend</b>", font=dict(size=12, family="Serif")), x=0.98, y=0.02, xanchor='right', yanchor='bottom', bgcolor="rgba(255, 255, 255, 0.9)", bordercolor="black", borderwidth=1, font=dict(family="Serif", size=10)),
            modebar=dict(orientation='h', bgcolor='rgba(255,255,255,0.5)'),
            dragmode='pan'
        )
        fig.add_annotation(text="<b>N</b><br>↑", showarrow=False, xref="paper", yref="paper", x=0.02, y=0.98, font=dict(size=18, family="Serif", color="black"), align="center", yanchor="top", xanchor="left")
        if x_range and y_range:
            span_x, span_y = x_range[1] - x_range[0], y_range[1] - y_range[0]
            pad_x, pad_y = span_x * 0.02, span_y * 0.02
            x_min_f, y_min_f = x_range[0] - pad_x, y_range[0] - pad_y
            fig.update_xaxes(range=[x_min_f, x_range[1]+pad_x], showticklabels=False, showgrid=False, zeroline=False, showline=True, linewidth=2.5, linecolor='black', mirror=True, ticks="")
            fig.update_yaxes(range=[y_min_f, y_range[1]+pad_y], scaleanchor="x", scaleratio=1, showticklabels=False, showgrid=False, zeroline=False, showline=True, linewidth=2.5, linecolor='black', mirror=True, ticks="")
            if span_x > 20000: dist, label = 5000, "5 km"
            elif span_x > 10000: dist, label = 2000, "2 km"
            elif span_x > 4000: dist, label = 1000, "1 km"
            else: dist, label = 500, "500 m"
            sc_x, sc_y = x_min_f + (span_x * 0.015), y_min_f + (span_y * 0.005)
            fig.add_trace(go.Scatter(x=[sc_x, sc_x + dist], y=[sc_y, sc_y], mode='lines', line=dict(color='black', width=3.5), showlegend=False, hoverinfo='skip'))
            fig.add_annotation(text=f"<b>{label}</b>", x=sc_x + (dist/2), y=sc_y, showarrow=False, yshift=8, font=dict(size=10, family="Serif", color="black"), xref="x", yref="y")
        if show_stats:
            fig.add_annotation(text=show_stats, align='left', showarrow=False, xref='paper', yref='paper', x=0.02, y=0.90, bgcolor="rgba(255, 255, 255, 0.85)", bordercolor="black", borderwidth=1, font=dict(family="Serif", size=10), xanchor="left", yanchor="top")

    def _write_centered_html(self, fig, path):
        config = {'displaylogo': False, 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d', 'resetScale2d'], 'scrollZoom': True}
        html_content = fig.to_html(full_html=False, include_plotlyjs='cdn', config=config)
        # Using string replacement instead of format() to avoid CSS brace conflicts
        template = """<html><head><meta charset="utf-8"><style>body { display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background-color: #dee2e6; overflow: hidden; } .map-container { background-color: #F1F3F0; box-shadow: 0 15px 45px rgba(0,0,0,0.2); width: 570px; height: 800px; position: relative; overflow: hidden; border: 1px solid #adb5bd; } .modebar-container { top: 85px !important; right: 35px !important; } .modebar-btn path { fill: #444 !important; }</style></head><body><div class="map-container">REPLACE_CONTENT</div></body></html>"""
        with open(path, "w", encoding='utf-8') as f:
            f.write(template.replace("REPLACE_CONTENT", html_content))

    def _add_osm_background(self, fig, network_gdf, green_gdf=None, water_gdf=None, build_gdf=None, limit_gdf=None, city_name=None, show_cycleways=True):
        use_water_bg = (limit_gdf is not None and not limit_gdf.empty)
        bg_color = "#D1D9DE" if use_water_bg else "#F4F3F0"
        
        # 1. Solid Land Polygon (under-layer for water background)
        if use_water_bg:
            for geom in limit_gdf.geometry:
                polys = [geom] if geom.geom_type == 'Polygon' else (list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [])
                for p in polys:
                    xs, ys = p.exterior.xy
                    fig.add_trace(go.Scatter(x=list(xs), y=list(ys), fill="toself", mode='none', fillcolor="#F4F3F0", opacity=1.0, showlegend=False, hoverinfo='skip'))
                    
        if water_gdf is not None and not water_gdf.empty:
            for geom in water_gdf.geometry:
                polys = [geom] if geom.geom_type == 'Polygon' else (list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [])
                for p in polys:
                    xs, ys = p.exterior.xy
                    fig.add_trace(go.Scatter(x=list(xs), y=list(ys), fill="toself", mode='none', fillcolor="#D1D9DE", opacity=0.85, showlegend=False, hoverinfo='skip'))
                if geom.geom_type in ['LineString', 'MultiLineString']:
                    lines = [geom] if geom.geom_type == 'LineString' else list(geom.geoms)
                    for l in lines:
                        xs, ys = l.xy
                        fig.add_trace(go.Scatter(x=list(xs), y=list(ys), mode='lines', line=dict(color="#D1D9DE", width=2), showlegend=False, hoverinfo='skip'))
        if build_gdf is not None and not build_gdf.empty:
            for geom in build_gdf.geometry:
                polys = [geom] if geom.geom_type == 'Polygon' else (list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [])
                for p in polys:
                    xs, ys = p.exterior.xy
                    fig.add_trace(go.Scatter(x=list(xs), y=list(ys), fill="toself", mode='none', fillcolor="#EBEAE5", opacity=0.9, showlegend=False, hoverinfo='skip'))
        if green_gdf is not None and not green_gdf.empty:
            for geom in green_gdf.geometry:
                polys = [geom] if geom.geom_type == 'Polygon' else (list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [])
                for p in polys:
                    xs, ys = p.exterior.xy
                    fig.add_trace(go.Scatter(x=list(xs), y=list(ys), fill="toself", mode='none', fillcolor="#D2DBD2", opacity=0.8, showlegend=False, hoverinfo='skip'))
        if limit_gdf is not None and not limit_gdf.empty:
            for geom in limit_gdf.geometry:
                lines = [geom] if geom.geom_type in ['LineString', 'Polygon'] else (list(geom.geoms) if geom.geom_type in ['MultiLineString', 'MultiPolygon'] else [])
                for line in lines:
                    xs, ys = (line.exterior.xy if line.geom_type == 'Polygon' else line.xy)
                    fig.add_trace(go.Scatter(x=list(xs), y=list(ys), mode='lines', line=dict(color="#C0C0C0", width=1.0, dash='dash'), showlegend=False, hoverinfo='skip'))
        if network_gdf is not None and not network_gdf.empty:
            main_hways = ['residential', 'tertiary', 'secondary', 'primary', 'trunk', 'motorway']
            main_net = network_gdf[network_gdf['highway'].isin(main_hways)]
            minor_net = network_gdf[~network_gdf['highway'].isin(main_hways)]
            cycle_net = network_gdf[network_gdf['original_highway'] == 'cycleway']
            
            traces = [
                (minor_net, "#CCCCCC", 0.45, "Minor Roads", False), 
                (main_net, "#FFFFFF", 0.85, "Major Roads", False)
            ]
            if show_cycleways:
                traces.append((cycle_net, "#3498DB", 1.2, "Existing Cycle Network", True))
                
            for net, color, width, name, show_leg in traces:
                if net.empty: continue
                xb, yb = [], []
                for geom in net.geometry:
                    lines = [geom] if geom.geom_type == 'LineString' else (list(geom.geoms) if geom.geom_type == 'MultiLineString' else [])
                    for line in lines:
                        xs, ys = line.xy
                        xb.extend(list(xs) + [None])
                        yb.extend(list(ys) + [None])
                fig.add_trace(go.Scatter(x=xb, y=yb, mode='lines', name=name, line=dict(color=color, width=width), showlegend=show_leg, connectgaps=False, hoverinfo='skip'))
        return bg_color

    def _add_positron_background(self, fig, network_gdf, green_gdf=None, water_gdf=None, build_gdf=None, limit_gdf=None, city_name=None):
        use_water_bg = (limit_gdf is not None and not limit_gdf.empty)
        bg_color = "#CBE2EE" if use_water_bg else "#F9F9FB"
        
        # 1. Solid Land Polygon (under-layer for water background)
        if use_water_bg:
            for geom in limit_gdf.geometry:
                polys = [geom] if geom.geom_type == 'Polygon' else (list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [])
                for p in polys:
                    xs, ys = p.exterior.xy
                    fig.add_trace(go.Scatter(x=list(xs), y=list(ys), fill="toself", mode='none', fillcolor="#F9F9FB", opacity=1.0, showlegend=False, hoverinfo='skip'))
                    
        if water_gdf is not None and not water_gdf.empty:
            for geom in water_gdf.geometry:
                polys = [geom] if geom.geom_type == 'Polygon' else (list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [])
                for p in polys:
                    xs, ys = p.exterior.xy
                    fig.add_trace(go.Scatter(x=list(xs), y=list(ys), fill="toself", mode='none', fillcolor="#CBE2EE", opacity=0.85, showlegend=False, hoverinfo='skip'))
                if geom.geom_type in ['LineString', 'MultiLineString']:
                    lines = [geom] if geom.geom_type == 'LineString' else list(geom.geoms)
                    for l in lines:
                        xs, ys = l.xy
                        fig.add_trace(go.Scatter(x=list(xs), y=list(ys), mode='lines', line=dict(color="#CBE2EE", width=2), showlegend=False, hoverinfo='skip'))
        if build_gdf is not None and not build_gdf.empty:
            for geom in build_gdf.geometry:
                polys = [geom] if geom.geom_type == 'Polygon' else (list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [])
                for p in polys:
                    xs, ys = p.exterior.xy
                    fig.add_trace(go.Scatter(x=list(xs), y=list(ys), fill="toself", mode='none', fillcolor="#F0EFEA", opacity=0.9, showlegend=False, hoverinfo='skip'))
        if green_gdf is not None and not green_gdf.empty:
            for geom in green_gdf.geometry:
                polys = [geom] if geom.geom_type == 'Polygon' else (list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [])
                for p in polys:
                    xs, ys = p.exterior.xy
                    fig.add_trace(go.Scatter(x=list(xs), y=list(ys), fill="toself", mode='none', fillcolor="#E8F0E8", opacity=0.8, showlegend=False, hoverinfo='skip'))
        if limit_gdf is not None and not limit_gdf.empty:
            for geom in limit_gdf.geometry:
                lines = [geom] if geom.geom_type in ['LineString', 'Polygon'] else (list(geom.geoms) if geom.geom_type in ['MultiLineString', 'MultiPolygon'] else [])
                for line in lines:
                    xs, ys = (line.exterior.xy if line.geom_type == 'Polygon' else line.xy)
                    fig.add_trace(go.Scatter(x=list(xs), y=list(ys), mode='lines', line=dict(color="#E0E0E0", width=1.0, dash='dash'), showlegend=False, hoverinfo='skip'))
        if network_gdf is not None and not network_gdf.empty:
            # Hierarchy mapping: motorway, trunk, primary, secondary, tertiary, residential, local
            motorway_net = network_gdf[network_gdf['highway'].isin(['motorway', 'trunk'])]
            primary_net = network_gdf[network_gdf['highway'] == 'primary']
            secondary_net = network_gdf[network_gdf['highway'].isin(['secondary', 'tertiary'])]
            minor_net = network_gdf[~network_gdf['highway'].isin(['motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'cycleway'])]
            cycle_net = network_gdf[network_gdf['original_highway'] == 'cycleway']
            
            for net, color, width, name in [
                (minor_net, "#C8C8C8", 0.40, "Local Roads"), 
                (secondary_net, "#A0A0A0", 0.70, "Collector Roads"),
                (primary_net, "#888888", 1.10, "Arterial Roads"),
                (motorway_net, "#666666", 1.60, "Motorways"),
                (cycle_net, "#b0d5b4", 1.5, "Existing Cycleways")
            ]:
                if net.empty: continue
                xb, yb = [], []
                for geom in net.geometry:
                    lines = [geom] if geom.geom_type == 'LineString' else (list(geom.geoms) if geom.geom_type == 'MultiLineString' else [])
                    for line in lines:
                        xs, ys = line.xy
                        xb.extend(list(xs) + [None])
                        yb.extend(list(ys) + [None])
                fig.add_trace(go.Scatter(x=xb, y=yb, mode='lines', name=name, line=dict(color=color, width=width), showlegend=False, connectgaps=False, hoverinfo='skip'))
        return bg_color

    def generate_h3_purpose_map(self, h3_gdf, network_gdf, scenario_id, column, title, color_rgb, legend_title="Trips (OD Survey)", bbox=None, p95_ref=None):
        '''
        Generates a standalone H3 purpose-specific density map with Positron background and logarithmic opacity scaling.
        '''
        xmin, ymin, xmax, ymax = bbox if bbox is not None else h3_gdf.total_bounds
        city_key = scenario_id.split('_')[0]
        srid = h3_gdf.crs.to_epsg() if h3_gdf.crs else 32719
        green, water, build, limit = self._ensure_context_layers(city_key, [xmin, ymin, xmax, ymax], srid)
        
        fig = go.Figure()
        bg_color = self._add_positron_background(fig, network_gdf, green, water, build, limit, city_name=city_key)
        
        # Calculate 95th percentile for log-based opacity scaling
        if p95_ref is not None:
            p95 = p95_ref
        else:
            valid_vals = h3_gdf[column].dropna()
            active_vals = valid_vals[valid_vals > 0.0]
            p95 = np.percentile(active_vals, 95) if not active_vals.empty else 1.0
            if p95 <= 0: p95 = 1.0
        
        # Resolve sequential ColorBrewer scale or single RGB color
        import plotly.colors as pc
        import re
        
        log_p95 = np.log1p(p95)
        is_scale = isinstance(color_rgb, str)
        if is_scale:
            colorscale_name = color_rgb
            scale_list = getattr(pc.sequential, colorscale_name, pc.sequential.OrRd)
        else:
            r, g, b = color_rgb
            scale_list = [f"rgb({r},{g},{b})", f"rgb({r},{g},{b})"]
            
        # Helper to sample color from colorscale
        def sample_colorscale(val):
            val = max(0.0, min(1.0, val))
            n = len(scale_list)
            idx = val * (n - 1)
            idx_low = int(np.floor(idx))
            idx_high = int(np.ceil(idx))
            c_low = scale_list[idx_low]
            c_high = scale_list[idx_high]
            
            r_l, g_l, b_l = map(int, re.findall(r'\d+', c_low))
            r_h, g_h, b_h = map(int, re.findall(r'\d+', c_high))
            
            frac = idx - idx_low
            r = int(r_l + frac * (r_h - r_l))
            g = int(g_l + frac * (g_h - g_l))
            b = int(b_l + frac * (b_h - b_l))
            return r, g, b

        # Draw hexagons with log-based color scaling
        for i, row in h3_gdf.iterrows():
            geom = row.geometry
            val = float(row[column] or 0.0)
            if val <= 0.0: continue
            
            # Logarithmic Scaling
            log_val = np.log1p(val)
            norm_val = min(1.0, log_val / log_p95)
            r_int, g_int, b_int = sample_colorscale(norm_val)
            
            # Opacity is constant 0.35 for color scales, or scaled for single colors
            opacity = 0.35 if is_scale else min(0.35, norm_val * 0.35)
            
            polys = [geom] if geom.geom_type == 'Polygon' else (list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [])
            for p in polys:
                xs, ys = p.exterior.xy
                h_text = f"Hexagon: {row.get('h3_index')}<br>Trips: {val:.1f}"
                fig.add_trace(go.Scatter(
                    x=list(xs), y=list(ys),
                    fill="toself",
                    mode='lines',
                    fillcolor=f"rgba({r_int}, {g_int}, {b_int}, {opacity:.6f})",
                    line=dict(color=f"rgba({r_int}, {g_int}, {b_int}, 0.050000)", width=0.5),
                    text=h_text,
                    hoverinfo='text',
                    showlegend=False
                ))
                
        # Generate raw ticks based on magnitude of p95
        raw_ticks = [1]
        for v in [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]:
            if v < p95 * 0.9:
                raw_ticks.append(v)
        if int(p95) not in raw_ticks and int(p95) > 1:
            raw_ticks.append(int(p95))
            
        # Map ticks to log space for Plotly colorbar
        tickvals = [np.log1p(v) for v in raw_ticks]
        ticktext = [f"{v} pers." for v in raw_ticks]
        
        # Build Plotly-compatible colorscale for the colorbar
        colorbar_colorscale = []
        for idx, c in enumerate(scale_list):
            frac = idx / (len(scale_list) - 1)
            rgba_c = c.replace("rgb(", "rgba(").replace(")", ", 0.35)")
            colorbar_colorscale.append([frac, rgba_c])
            
        # Add a dummy trace to display a continuous colorscale legend (colorbar)
        colorbar_trace = go.Scatter(
            x=[None],
            y=[None],
            mode='markers',
            marker=dict(
                colorscale=colorbar_colorscale,
                cmin=0,
                cmax=log_p95,
                color=[0, log_p95],
                showscale=True,
                colorbar=dict(
                    title=dict(text=f"<b>{legend_title}</b>", font=dict(size=10, family="Serif")),
                    tickfont=dict(family="Serif", size=10),
                    tickvals=tickvals,
                    ticktext=ticktext,
                    thickness=8,
                    len=0.30,
                    x=0.98,
                    y=0.05,
                    xanchor="right",
                    yanchor="bottom",
                    bgcolor="rgba(255,255,255,0.85)"
                )
            ),
            showlegend=False,
            hoverinfo='skip'
        )
        fig.add_trace(colorbar_trace)
                 
        # Scale and Layout (automatically calculated inside layout method)
        self._apply_academic_layout(fig, title, x_range=[xmin, xmax], y_range=[ymin, ymax], bg_color="#F9F9FB")
        
        # Centered HTML output path
        filename = f"{scenario_id}_{column}_map.html"
        output_path = os.path.join(self.output_dir, filename)
        self._write_centered_html(fig, output_path)
        
        print(f"   - [Plotly] Standalone H3 Purpose Map generated: {output_path}")
        return output_path

    def generate_impedance_map(self, network_gdf, scenario_id, bbox=None):
        mask_col = 'participating_in_analysis'
        fg_gdf = network_gdf[network_gdf[mask_col] == True] if mask_col in network_gdf.columns else network_gdf
        xmin, ymin, xmax, ymax = bbox if bbox is not None else fg_gdf.total_bounds
        city_key = scenario_id.split('_')[0]
        srid = network_gdf.crs.to_epsg() if network_gdf.crs else 32719
        green, water, build, limit = self._ensure_context_layers(city_key, [xmin, ymin, xmax, ymax], srid)
        fig = go.Figure()
        bg_color = self._add_osm_background(fig, network_gdf, green, water, build, limit, city_name=city_key, show_cycleways=False)
        style_map = {
            'primary': {'color': '#e91e63', 'width': 1.6, 'label': 'Primary Road'}, 
            'secondary': {'color': '#ff9800', 'width': 1.2, 'label': 'Secondary Road'}, 
            'tertiary': {'color': '#9c27b0', 'width': 0.9, 'label': 'Tertiary Road'}, 
            'residential': {'color': '#2196f3', 'width': 0.8, 'label': 'Residential Street'},
            'cycleway': {'color': '#27ae60', 'width': 2.0, 'label': 'Existing Cycleway'},
            'project_new': {'color': '#e67e22', 'width': 2.5, 'label': 'New Project (+Ciclo)'}
        }
        for typ in ['primary', 'secondary', 'tertiary', 'residential', 'cycleway', 'project_new']:
            subset = fg_gdf[fg_gdf['highway'] == typ]
            if subset.empty: continue
            style = style_map[typ]
            xb, yb, hover = [], [], []
            for geom in subset.geometry:
                h_text = f"Type: {style['label']}"
                lines = [geom] if geom.geom_type == 'LineString' else list(geom.geoms)
                for line in lines:
                    xs, ys = line.xy
                    xb.extend(list(xs) + [None])
                    yb.extend(list(ys) + [None])
                    hover.extend([h_text] * (len(xs) + 1))
            fig.add_trace(go.Scatter(x=xb, y=yb, mode='lines', name=style['label'], line=dict(color=style['color'], width=style['width']), connectgaps=False, hoverinfo='text', text=hover))
        self._apply_academic_layout(fig, f"Road Typology: {scenario_id}", x_range=[xmin, xmax], y_range=[ymin, ymax], bg_color=bg_color)
        path = os.path.join(self.output_dir, f"{scenario_id}_impedance.html")
        self._write_centered_html(fig, path)
        return path

    def generate_flow_map(self, network_gdf, scenario_id, type="baseline", bbox=None, total_trips=1.0, flow_type="all"):
        mask_col = 'participating_in_analysis'
        fg_gdf = network_gdf[network_gdf[mask_col] == True] if mask_col in network_gdf.columns else network_gdf
        xmin, ymin, xmax, ymax = bbox if bbox is not None else fg_gdf.total_bounds
        city_key = scenario_id.split('_')[0]
        srid = network_gdf.crs.to_epsg() if network_gdf.crs else 32719
        green, water, build, limit = self._ensure_context_layers(city_key, [xmin, ymin, xmax, ymax], srid)
        fig = go.Figure()
        bg_color = self._add_osm_background(fig, network_gdf, green, water, build, limit, city_name=city_key, show_cycleways=False)

        if flow_type == "bikelanes":
            # Add all streets as background Positron-style layout
            bg_width_map = {
                'primary': 1.2,
                'secondary': 0.9,
                'tertiary': 0.7,
                'residential': 0.5
            }
            # We draw all streets from fg_gdf as background reference
            for hw_type, w_val in bg_width_map.items():
                if hw_type == 'residential':
                    sub_gdf = fg_gdf[fg_gdf['original_highway'].isin(['residential', 'cycleway', None, '']) | fg_gdf['original_highway'].isnull()]
                else:
                    sub_gdf = fg_gdf[fg_gdf['original_highway'] == hw_type]
                
                if sub_gdf.empty: continue
                xb_bg, yb_bg = [], []
                for geom in sub_gdf.geometry:
                    lines = [geom] if geom.geom_type == 'LineString' else list(geom.geoms)
                    for line in lines:
                        xs, ys = line.xy
                        xb_bg.extend(list(xs) + [None])
                        yb_bg.extend(list(ys) + [None])
                
                fig.add_trace(go.Scatter(
                    x=xb_bg, y=yb_bg,
                    mode='lines',
                    line=dict(color='#dcdfe3', width=w_val),
                    connectgaps=False,
                    hoverinfo='skip',
                    showlegend=False
                ))

            # Draw all existing cycleways as a very soft, light-green reference background trace
            all_cycleways = fg_gdf[fg_gdf['original_highway'] == 'cycleway']
            if not all_cycleways.empty:
                xc_bg, yc_bg = [], []
                for geom in all_cycleways.geometry:
                    lines = [geom] if geom.geom_type == 'LineString' else list(geom.geoms)
                    for line in lines:
                        xs, ys = line.xy
                        xc_bg.extend(list(xs) + [None])
                        yc_bg.extend(list(ys) + [None])
                fig.add_trace(go.Scatter(
                    x=xc_bg, y=yc_bg,
                    mode='lines',
                    line=dict(color='#b0d5b4', width=1.5, dash='solid'), # Soft desaturated green solid line
                    connectgaps=False,
                    hoverinfo='skip',
                    showlegend=False
                ))

        flow_gdf = fg_gdf[fg_gdf['od_flow'] > 0]
        if not flow_gdf.empty:
            max_f = flow_gdf['od_flow'].max()
            quantiles = np.quantile(flow_gdf['od_flow'], [0, 0.5, 0.75, 0.9, 0.97, 1.0])
            
            if flow_type == "bikelanes":
                draw_gdf = flow_gdf[flow_gdf['original_highway'] == 'cycleway']
                colors = ["#c8e6c9", "#81c784", "#4caf50", "#2e7d32", "#1b5e20"]
                # Keep full network quantiles for synchronized scaling (ADR 0003)
            else:
                draw_gdf = flow_gdf
                colors = px.colors.sequential.YlOrRd[2:7]

            for i in range(5):
                q_min, q_max = quantiles[i], quantiles[i+1]
                bucket = draw_gdf[(draw_gdf['od_flow'] >= q_min) & (draw_gdf['od_flow'] <= q_max)]
                if bucket.empty: continue
                label = f"{int(q_min)} - {int(q_max)} trips"
                
                if flow_type == "bikelanes":
                    # Draw all segments of the same thickness (constant width 3.0)
                    xb, yb, hover = [], [], []
                    for _, row in bucket.iterrows():
                        flow_val = float(row['od_flow'] or 0)
                        h_text = f"Flow: {int(flow_val)} trips"
                        if row.get('original_highway') and str(row.get('original_highway')) != 'None':
                            h_text += f"<br>Hierarchy: {row.get('original_highway')}"
                        
                        lines = [row.geometry] if row.geometry.geom_type == 'LineString' else list(row.geometry.geoms)
                        for line in lines:
                            xs, ys = line.xy
                            xb.extend(list(xs) + [None])
                            yb.extend(list(ys) + [None])
                            hover.extend([h_text] * (len(xs) + 1))
                    
                    fig.add_trace(go.Scatter(
                        x=xb, y=yb, 
                        mode='lines', 
                        name=label, 
                        line=dict(color=colors[i], width=3.0), 
                        connectgaps=False, 
                        hoverinfo='text', 
                        text=hover
                    ))
                else:
                    xb, yb, hover = [], [], []
                    for _, row in bucket.iterrows():
                        flow_val = float(row['od_flow'] or 0)
                        h_text = f"Flow: {int(flow_val)} trips"
                        
                        if row.get('highway') == 'cycleway':
                            h_text += "<br>Cycleway: Yes"
                        
                        # Segment-wise PCR calculation
                        if row.get('project_id') and str(row.get('project_id')) != 'None':
                            pcr = (flow_val / total_trips) * 100.0
                            h_text += f"<br><b>Project: {row['project_id']}</b>"
                            if pcr > 0:
                                h_text += f"<br>Segment Capture (PCR): {pcr:.2f}% ({int(flow_val)} / {int(total_trips)})"
                        
                        lines = [row.geometry] if row.geometry.geom_type == 'LineString' else list(row.geometry.geoms)
                        for line in lines:
                            xs, ys = line.xy
                            xb.extend(list(xs) + [None])
                            yb.extend(list(ys) + [None])
                            hover.extend([h_text] * (len(xs) + 1))
                            
                    w = 1.0 + (bucket['od_flow'].mean() / max_f) * 4.0 if max_f > 0 else 1.0
                    fig.add_trace(go.Scatter(x=xb, y=yb, mode='lines', name=label, line=dict(color=colors[i], width=w), connectgaps=False, hoverinfo='text', text=hover))

        title_en = "Baseline Flow" if type == "baseline" else "Scenario Flow"
        if flow_type == "bikelanes":
            title_en += " (Cycleways)"
        else:
            title_en += " (Full Network)"
            
        self._apply_academic_layout(fig, f"{title_en}: {scenario_id}", x_range=[xmin, xmax], y_range=[ymin, ymax], bg_color=bg_color)
        
        file_suffix = "_flow_bikelanes.html" if flow_type == "bikelanes" else f"_{type}_flow.html"
        path = os.path.join(self.output_dir, f"{scenario_id}{file_suffix}")
        self._write_centered_html(fig, path)
        return path

    def generate_delta_sigma_map(self, delta_gdf, scenario_id, bbox=None, context_gdf=None):
        mask_col = 'participating_in_analysis'
        fg_gdf = delta_gdf[delta_gdf[mask_col] == True] if mask_col in delta_gdf.columns else delta_gdf
        xmin, ymin, xmax, ymax = bbox if bbox is not None else fg_gdf.total_bounds
        city_key = scenario_id.split('_')[0]
        srid = delta_gdf.crs.to_epsg() if delta_gdf.crs else 32719
        green, water, build, limit = self._ensure_context_layers(city_key, [xmin, ymin, xmax, ymax], srid)
        fig = go.Figure()
        bg_color = self._add_osm_background(fig, context_gdf if context_gdf is not None else delta_gdf, green, water, build, limit, city_name=city_key, show_cycleways=False)
        if not fg_gdf.empty:
            neg = fg_gdf[fg_gdf['delta_flow'] < 0]['delta_flow']
            pos = fg_gdf[fg_gdf['delta_flow'] > 0]['delta_flow']
            neg_abs = neg.abs()
            q_neg_abs = np.quantile(neg_abs, [0, 0.50, 0.875, 0.975, 1.0]) if not neg.empty else [0, 1, 2, 3, 4]
            q_pos = np.quantile(pos, [0, 0.50, 0.875, 0.975, 1.0]) if not pos.empty else [0, 1, 2, 3, 4]
            colors = ["#b2182b", "#d6604d", "#f4a582", "#fddbc7", "#e0e0e0", "#d1e5f0", "#92c5de", "#4393c3", "#2166ac"]
            labels = [
                "Critical Reduction (Top 2.5% Drop)", "Major Reduction (87.5-97.5% Drop)", "Medium Reduction (50-87.5% Drop)", "Light Reduction (0-50% Drop)",
                "No Change",
                "Light Increase (0-50% Gain)", "Medium Increase (50-87.5% Gain)", "Major Increase (87.5-97.5% Gain)", "Critical Peak Increase (Top 2.5% Gain)"
            ]
            for i in range(9):
                if i == 0: cond = (fg_gdf['delta_flow'] < -q_neg_abs[3])
                elif i == 1: cond = (fg_gdf['delta_flow'] >= -q_neg_abs[3]) & (fg_gdf['delta_flow'] < -q_neg_abs[2])
                elif i == 2: cond = (fg_gdf['delta_flow'] >= -q_neg_abs[2]) & (fg_gdf['delta_flow'] < -q_neg_abs[1])
                elif i == 3: cond = (fg_gdf['delta_flow'] >= -q_neg_abs[1]) & (fg_gdf['delta_flow'] < 0)
                elif i == 4: cond = (fg_gdf['delta_flow'] == 0)
                elif i == 5: cond = (fg_gdf['delta_flow'] > 0) & (fg_gdf['delta_flow'] <= q_pos[1])
                elif i == 6: cond = (fg_gdf['delta_flow'] > q_pos[1]) & (fg_gdf['delta_flow'] <= q_pos[2])
                elif i == 7: cond = (fg_gdf['delta_flow'] > q_pos[2]) & (fg_gdf['delta_flow'] <= q_pos[3])
                else: cond = (fg_gdf['delta_flow'] > q_pos[3])
                subset = fg_gdf[cond]
                if subset.empty: continue
                v_min, v_max = subset['delta_flow'].min(), subset['delta_flow'].max()
                label = f"{labels[i]} ({int(v_min)} to {int(v_max)})"
                xb, yb, hover = [], [], []
                for _, row in subset.iterrows():
                    h_text = f"Change: {int(row['delta_flow'])}"
                    lines = [row.geometry] if row.geometry.geom_type == 'LineString' else list(row.geometry.geoms)
                    for line in lines:
                        xs, ys = line.xy
                        xb.extend(list(xs) + [None])
                        yb.extend(list(ys) + [None])
                        hover.extend([h_text] * (len(xs) + 1))
                w = 1.0 + (subset['delta_flow'].abs().mean() / max_abs) * 4.0 if max_abs > 0 else 1.0
                fig.add_trace(go.Scatter(x=xb, y=yb, mode='lines', name=label, line=dict(color=colors[i], width=w), connectgaps=False, hoverinfo='text', text=hover))
        self._apply_academic_layout(fig, f"Change Analysis: {scenario_id}", x_range=[xmin, xmax], y_range=[ymin, ymax], bg_color=bg_color)
        path = os.path.join(self.output_dir, f"{scenario_id}_delta_sigma.html")
        self._write_centered_html(fig, path)
        return path

    def generate_project_performance_map(self, network_gdf, scenario_id, bbox=None, total_trips=1.0):
        print("   - [Plotly] Generating Segment-wise Project Performance Map...")
        # Robust detection using project_id or is_project flag
        is_proj_mask = (network_gdf['project_id'].notnull())
        if 'is_project' in network_gdf.columns:
            is_proj_mask = is_proj_mask | (network_gdf['is_project'] == True)
        p_gdf = network_gdf[is_proj_mask].copy()
        if p_gdf.empty: return None
        
        mask_col = 'participating_in_analysis'
        fg_gdf = network_gdf[network_gdf[mask_col] == True] if mask_col in network_gdf.columns else network_gdf
        xmin, ymin, xmax, ymax = bbox if bbox is not None else fg_gdf.total_bounds
        city_key = scenario_id.split('_')[0]
        srid = network_gdf.crs.to_epsg() if network_gdf.crs else 32719
        green, water, build, limit = self._ensure_context_layers(city_key, [xmin, ymin, xmax, ymax], srid)
        
        fig = go.Figure()
        bg_color = self._add_osm_background(fig, network_gdf, green, water, build, limit, city_name=city_key, show_cycleways=False)
        
        # 1. Compute quantiles using the whole network's active flow to match the flow map's scale
        net_flow = network_gdf[network_gdf['od_flow'] > 0]['od_flow']
        if not net_flow.empty:
            quantiles = np.quantile(net_flow, [0, 0.5, 0.75, 0.9, 0.97, 1.0])
        else:
            quantiles = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]

        colors = ["#c8e6c9", "#81c784", "#4caf50", "#2e7d32", "#1b5e20"]
        labels = ["Local Use", "Connector Use", "Trunk Use", "Critical Use", "Strategic Artery"]

        # 2. Draw existing cycleways (non-project) as a single solid light blue continuous trace
        orig_cycle_mask = (network_gdf['original_highway'] == 'cycleway') if 'original_highway' in network_gdf.columns else (network_gdf['highway'] == 'cycleway')
        cycle_gdf = network_gdf[orig_cycle_mask & (~is_proj_mask)].copy()
        if not cycle_gdf.empty:
            xc, yc, hover = [], [], []
            for _, row in cycle_gdf.iterrows():
                flow_val = float(row['od_flow'] or 0)
                if flow_val > 0.0:
                    h_text = f"Existing Cycleway<br>Flow: {int(flow_val)} trips"
                else:
                    h_text = "Existing Cycleway (No Flow)"
                
                lines = [row.geometry] if row.geometry.geom_type == 'LineString' else list(row.geometry.geoms)
                for line in lines:
                    xs, ys = line.xy
                    xc.extend(list(xs) + [None])
                    yc.extend(list(ys) + [None])
                    hover.extend([h_text] * (len(xs) + 1))
            
            fig.add_trace(go.Scatter(
                x=xc, y=yc,
                mode='lines',
                name="Existing Cycleway",
                line=dict(color='#4fa8e3', width=2.0, dash='solid'),
                connectgaps=False,
                hoverinfo='text',
                text=hover,
                showlegend=True
            ))

        # 3. Draw proposed project / recommended segments
        is_rec = scenario_id.startswith("rec_")
        prefix = "Recommended" if is_rec else "Project"
        
        for i in range(5):
            q_min = quantiles[i] if i > 0 else -1.0
            q_max = quantiles[i+1]
            bucket = p_gdf[(p_gdf['od_flow'] >= q_min) & (p_gdf['od_flow'] <= q_max)]
            if bucket.empty: continue
            
            xb, yb, hover = [], [], []
            for _, row in bucket.iterrows():
                f_val = float(row['od_flow'] or 0)
                pcr = (f_val / total_trips) * 100.0 if total_trips > 0 else 0.0
                p_id = row.get('project_id')
                if p_id is not None and str(p_id) != 'None' and str(p_id).strip() != '':
                    h_text = f"<b>Project: {p_id}</b>"
                elif is_rec:
                    h_text = f"<b>Recommended Corridor</b>"
                else:
                    h_text = f"<b>Proposed Project Corridor</b>"
                h_text += f"<br>Segment Load: {int(f_val)} trips"
                h_text += f"<br>Capture (PCR): {pcr:.2f}% ({int(f_val)} / {int(total_trips)})"
                
                lines = [row.geometry] if row.geometry.geom_type == 'LineString' else list(row.geometry.geoms)
                for line in lines:
                    xs, ys = line.xy
                    xb.extend(list(xs) + [None])
                    yb.extend(list(ys) + [None])
                    hover.extend([h_text] * (len(xs) + 1))
            
            q_min_lbl = int(quantiles[i]) if i > 0 else 0
            q_max_lbl = int(quantiles[i+1])
            fig.add_trace(go.Scatter(
                x=xb, y=yb,
                mode='lines',
                name=f"{prefix} ({q_min_lbl} - {q_max_lbl} trips)",
                line=dict(color=colors[i], width=3.0, dash='solid'),
                connectgaps=False,
                hoverinfo='text',
                text=hover
            ))
        
        self._apply_academic_layout(fig, f"Segment Performance: {scenario_id}", x_range=[xmin, xmax], y_range=[ymin, ymax], show_stats=None, bg_color=bg_color)
        path = os.path.join(self.output_dir, f"{scenario_id}_project_performance.html")
        self._write_centered_html(fig, path)
        return path

    def compile_report(self, scenario_id, map_paths, project_metrics=None):
        print(f"   - [Plotly] Compiling Impact Dashboard for {scenario_id}...")
        contents, labels = [], ["Baseline Flow (Full Network)", "Baseline Flow (Cycleways)", "Scenario Flow (Full Network)", "Change Analysis (Δ)"]
        for i, p in enumerate(map_paths):
            if p and os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    inner = f.read().split('<div class="map-container">')[1].split('</body>')[0].strip().rsplit('</div>', 1)[0]
                    contents.append(f"<div class='map-label'>{labels[i]}</div>" + inner)
            else: contents.append(f"<div class='map-label'>{labels[i]}</div><div style='display:flex;align-items:center;justify-content:center;height:800px;background:#eee;font-family:Serif;color:#666;'>Data for {labels[i]} not found</div>")
        
        # Build metrics table HTML if provided
        metrics_html = ""
        if project_metrics:
            metrics_html = f"""
            <div class="metrics-container">
              <div class="metrics-title">Suggested Project Performance Metrics</div>
              <table class="metrics-table">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Value</th>
                    <th>Interpretation</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><b>Total Length</b></td>
                    <td>{project_metrics['length']:.1f} m</td>
                    <td>Total linear length of streets upgraded to cycleway standards.</td>
                  </tr>
                  <tr>
                    <td><b>Est. Construction Cost</b></td>
                    <td>${project_metrics['cost']:,.2f} USD</td>
                    <td>Calculated using average standard unit cost of $100/m.</td>
                  </tr>
                  <tr>
                    <td><b>Avg Routed Flow</b></td>
                    <td>{project_metrics['avg_flow']:.2f} active trips/day</td>
                    <td>Mean active mobility traffic volume utilizing the upgraded lanes.</td>
                  </tr>
                  <tr>
                    <td><b>Peak Routed Flow</b></td>
                    <td>{project_metrics['max_flow']:.2f} active trips/day</td>
                    <td>Maximum volume captured at the project's highest attraction node.</td>
                  </tr>
                  <tr>
                    <td><b>Project Capture Rate (PCR)</b></td>
                    <td>{project_metrics['pcr']:.2f}%</td>
                    <td>Percentage of total successfully routed city trips using this infrastructure.</td>
                  </tr>
                </tbody>
              </table>
            </div>
            """

        # Using string replacement instead of format() to avoid CSS brace conflicts
        template = """<html><head><meta charset="utf-8"><title>+Ciclo Impact Dashboard: SCENARIO_ID</title><style>body { display: flex; flex-direction: column; align-items: center; background-color: #adb5bd; margin: 0; padding: 20px; font-family: Serif; } .dashboard-title { font-size: 24px; font-weight: bold; margin-bottom: 20px; color: #212529; } .metrics-container { background: #F1F3F0; border-radius: 8px; padding: 15px 20px; width: 95vw; max-width: 1200px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); border: 1px solid #343a40; text-align: left; } .metrics-title { font-size: 18px; font-weight: bold; margin-bottom: 10px; color: #212529; border-bottom: 2px solid #495057; padding-bottom: 5px; } .metrics-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px; } .metrics-table th, .metrics-table td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #dee2e6; } .metrics-table th { background-color: #495057; color: white; font-weight: bold; } .metrics-table tr:hover { background-color: #e9ecef; } .grid-container { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; width: 95vw; max-width: 1200px; } .map-wrapper { display: flex; flex-direction: column; align-items: center; background: #F1F3F0; border-radius: 8px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.2); border: 1px solid #343a40; } .map-label { background: #495057; color: white; width: 100%; text-align: center; padding: 8px 0; font-size: 16px; font-weight: bold; } .map-container { width: 570px; height: 800px; position: relative; overflow: hidden; transform: scale(0.85); transform-origin: top center; margin-bottom: -120px; } .modebar-container { top: 85px !important; right: 35px !important; } .modebar-btn path { fill: #444 !important; }</style><script src="https://cdn.plot.ly/plotly-3.5.0.min.js"></script></head><body><div class="dashboard-title">+Ciclo Impact Dashboard | Scenario: SCENARIO_ID</div>METRICS_TABLE<div class="grid-container"><div class="map-wrapper"><div class="map-container">MAP0</div></div><div class="map-wrapper"><div class="map-container">MAP1</div></div><div class="map-wrapper"><div class="map-container">MAP2</div></div><div class="map-wrapper"><div class="map-container">MAP3</div></div></div><script>var containers = document.getElementsByClassName('plotly-graph-div'); function sync(eventData) { if (!eventData['xaxis.range[0]']) return; for (var i = 0; i < containers.length; i++) { if (containers[i] !== this) { Plotly.relayout(containers[i], { 'xaxis.range': [eventData['xaxis.range[0]'], eventData['xaxis.range[1]']], 'yaxis.range': [eventData['yaxis.range[0]'], eventData['yaxis.range[1]']] }); } } } setTimeout(function(){ for (var i = 0; i < containers.length; i++) { containers[i].on('plotly_relayout', sync); } }, 1500);</script></body></html>"""
        d_html = template.replace("SCENARIO_ID", scenario_id).replace("METRICS_TABLE", metrics_html)
        for i, content in enumerate(contents):
            d_html = d_html.replace(f"MAP{i}", content)
            
        r_path = os.path.join(self.output_dir, f"{scenario_id}_COMPLIED_REPORT.html")
        with open(r_path, "w", encoding='utf-8') as f: f.write(d_html)
        return r_path

    def generate_flow_purpose_map(self, network_gdf, baseline_net_gdf, scenario_id, column, title, color_rgb, legend_title="Purpose Flow", bbox=None, max_flow_ref=None, quantiles_ref=None):
        '''
        Generates a standalone purpose-specific network flow map with Positron background and unified log-quantiles scale.
        '''
        xmin, ymin, xmax, ymax = bbox if bbox is not None else network_gdf.total_bounds
        city_key = scenario_id.split('_')[0]
        srid = network_gdf.crs.to_epsg() if network_gdf.crs else 32719
        green, water, build, limit = self._ensure_context_layers(city_key, [xmin, ymin, xmax, ymax], srid)
        
        fig = go.Figure()
        bg_color = self._add_osm_background(fig, network_gdf, green, water, build, limit, city_name=city_key, show_cycleways=False)
        
        # Add all streets as background reference Positron-style layout
        bg_width_map = {
            'primary': 1.2,
            'secondary': 0.9,
            'tertiary': 0.7,
            'residential': 0.5
        }
        for hw_type, w_val in bg_width_map.items():
            if hw_type == 'residential':
                sub_gdf = network_gdf[network_gdf['original_highway'].isin(['residential', 'cycleway', None, '']) | network_gdf['original_highway'].isnull()]
            else:
                sub_gdf = network_gdf[network_gdf['original_highway'] == hw_type]
            
            if sub_gdf.empty: continue
            xb_bg, yb_bg = [], []
            for geom in sub_gdf.geometry:
                lines = [geom] if geom.geom_type == 'LineString' else list(geom.geoms)
                for line in lines:
                    xs, ys = line.xy
                    xb_bg.extend(list(xs) + [None])
                    yb_bg.extend(list(ys) + [None])
            
            fig.add_trace(go.Scatter(
                x=xb_bg, y=yb_bg,
                mode='lines',
                line=dict(color='#dcdfe3', width=w_val),
                connectgaps=False,
                hoverinfo='skip',
                showlegend=False
            ))

        # Get overall flow reference bounds from reference if provided
        if max_flow_ref is not None and quantiles_ref is not None:
            max_overall_f = max_flow_ref
            quantiles = quantiles_ref
        else:
            ref_flow_gdf = network_gdf[network_gdf[column] > 0]
            if not ref_flow_gdf.empty:
                max_overall_f = ref_flow_gdf[column].max()
                quantiles = np.quantile(ref_flow_gdf[column], [0, 0.5, 0.75, 0.9, 0.97, 1.0])
            else:
                max_overall_f = 1.0
                quantiles = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]

        # Draw flow segments divided by overall quantiles to guarantee comparison parity
        r, g, b = color_rgb
        opacities = [0.15, 0.35, 0.60, 0.80, 1.0]
        
        flow_gdf = network_gdf[network_gdf[column] > 0]
        if not flow_gdf.empty:
            for i in range(5):
                q_min, q_max = quantiles[i], quantiles[i+1]
                bucket = flow_gdf[(flow_gdf[column] >= q_min) & (flow_gdf[column] <= q_max)]
                if bucket.empty: continue
                label = f"{int(q_min)} - {int(q_max)} trips"
                
                xb, yb, hover = [], [], []
                for _, row in bucket.iterrows():
                    flow_val = float(row[column] or 0)
                    h_text = f"Purpose Flow: {int(flow_val)} trips"
                    if row.get('original_highway') and str(row.get('original_highway')) != 'None':
                        h_text += f"<br>Hierarchy: {row.get('original_highway')}"
                    
                    lines = [row.geometry] if row.geometry.geom_type == 'LineString' else list(row.geometry.geoms)
                    for line in lines:
                        xs, ys = line.xy
                        xb.extend(list(xs) + [None])
                        yb.extend(list(ys) + [None])
                        hover.extend([h_text] * (len(xs) + 1))
                
                # Settle thickness based on purpose flow weight relative to overall maximum
                w = 1.0 + (bucket[column].mean() / max_overall_f) * 4.0 if max_overall_f > 0 else 1.0
                fig.add_trace(go.Scatter(
                    x=xb, y=yb,
                    mode='lines',
                    name=label,
                    line=dict(color=f"rgba({r}, {g}, {b}, {opacities[i]})", width=w),
                    connectgaps=False,
                    hoverinfo='text',
                    text=hover
                ))

        self._apply_academic_layout(fig, f"{title}: {scenario_id}", x_range=[xmin, xmax], y_range=[ymin, ymax], bg_color=bg_color)
        
        path = os.path.join(self.output_dir, f"{scenario_id}_flow_{legend_title.lower().replace(' ', '_')}.html")
        self._write_centered_html(fig, path)
        return path

if __name__ == "__main__":
    print("Plotly Academic Map Generator ready.")
