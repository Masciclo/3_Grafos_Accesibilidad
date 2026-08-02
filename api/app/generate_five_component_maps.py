import os
import sys
import geopandas as gpd
import networkx as nx
import plotly.graph_objects as go
from sqlalchemy import create_engine

from core.academic_maps import AcademicMapGenerator

def main():
    print("🎨 Generating Dual 5-Component Intervened Maps for Santiago...")
    engine = create_engine('postgresql://ciclo:ciclo@stationdb:5432/ciclo_dev')

    # Load baseline network and recommendation network
    net_gdf = gpd.read_postgis("SELECT * FROM santchil_current_internal_net", engine, geom_col='geometry')
    rec_gdf = gpd.read_postgis("SELECT * FROM santchil_rec_1785604682_network", engine, geom_col='geometry')

    # Detect top 5 cycleway clusters using NetworkX Graph Traversal
    cycle_gdf = net_gdf[net_gdf['highway'] == 'cycleway'].copy()
    G = nx.Graph()
    for _, r in cycle_gdf.iterrows():
        G.add_edge(r['source'], r['target'], id=r['id'])

    comps = sorted(nx.connected_components(G), key=len, reverse=True)
    top5_comps = comps[:5]

    # Map edge_id -> cluster index (1 to 5)
    edge_to_cluster = {}
    for cluster_idx, comp_nodes in enumerate(top5_comps):
        sub = G.subgraph(comp_nodes)
        for u, v, d in sub.edges(data=True):
            edge_to_cluster[d['id']] = cluster_idx + 1

    # Exact palette requested by user
    palette = {
        1: "#F20574",  # Magenta / Pink (Cluster 1: Main Metropolitan Network)
        2: "#763DF2",  # Purple (Cluster 2: Sector Conchalí / Norte)
        3: "#3D8BF2",  # Blue (Cluster 3: Sector Peñalolén / Oriente)
        4: "#F2A30F",  # Gold / Amber (Cluster 4: Sector La Cisterna / Sur)
        5: "#F2490C",  # Red-Orange (Cluster 5: Sector Pudahuel-Maipú / Poniente)
    }

    cluster_names = {
        1: "Cluster 1: Main Metropolitan Network (4,541 edges)",
        2: "Cluster 2: Sector Conchalí Subnetwork (392 edges)",
        3: "Cluster 3: Sector Peñalolén Subnetwork (309 edges)",
        4: "Cluster 4: Sector La Cisterna Subnetwork (298 edges)",
        5: "Cluster 5: Sector Pudahuel-Maipú Subnetwork (276 edges)",
    }

    output_dir = "/app/data/santiago/out/maps"
    if not os.path.exists("/app"):
        output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "santiago", "out", "maps"))
    os.makedirs(output_dir, exist_ok=True)
    generator = AcademicMapGenerator(output_dir=output_dir)

    bbox = net_gdf.total_bounds
    xmin, ymin, xmax, ymax = bbox
    # Skip slow Overpass API background downloads for instant rendering
    green, water, build, limit = None, None, None, None

    # -------------------------------------------------------------
    # MAP 1: CURRENT SCENARIO (DISCONNECTED BASELINE)
    # -------------------------------------------------------------
    print("   - [Map 1/2] Rendering Disconnected Current Scenario...")
    fig1 = go.Figure()
    bg_color = generator._add_osm_background(fig1, net_gdf, green, water, build, limit, city_name="santiago", show_cycleways=False)

    # Render neutral background cycleways (Clusters 6 to 348)
    other_cycles = cycle_gdf[~cycle_gdf['id'].isin(edge_to_cluster.keys())]
    if not other_cycles.empty:
        xo, yo = [], []
        for geom in other_cycles.geometry:
            lines = [geom] if geom.geom_type == 'LineString' else list(geom.geoms)
            for l in lines:
                xs, ys = l.xy
                xo.extend(list(xs) + [None])
                yo.extend(list(ys) + [None])
        fig1.add_trace(go.Scatter(
            x=xo, y=yo, mode='lines', name='Other Secondary Cycleways',
            line=dict(color='#CFD8DC', width=1.0), connectgaps=False, hoverinfo='skip', showlegend=True
        ))

    # Render the 5 Intervened Clusters in their exact colors
    for c_id in range(1, 6):
        c_edges = cycle_gdf[cycle_gdf['id'].isin([eid for eid, cid in edge_to_cluster.items() if cid == c_id])]
        if c_edges.empty: continue
        xc, yc, hover = [], [], []
        for _, r in c_edges.iterrows():
            h_text = f"<b>{cluster_names[c_id]}</b><br>Edge ID: {r['id']}"
            lines = [r.geometry] if r.geometry.geom_type == 'LineString' else list(r.geometry.geoms)
            for l in lines:
                xs, ys = l.xy
                xc.extend(list(xs) + [None])
                yc.extend(list(ys) + [None])
                hover.extend([h_text] * (len(xs) + 1))

        fig1.add_trace(go.Scatter(
            x=xc, y=yc, mode='lines', name=cluster_names[c_id],
            line=dict(color=palette[c_id], width=2.8), connectgaps=False, hoverinfo='text', text=hover
        ))

    generator._apply_academic_layout(fig1, "Santiago Disconnected Baseline Scenario", x_range=[xmin, xmax], y_range=[ymin, ymax], bg_color=bg_color)
    path1 = os.path.join(output_dir, "santiago_5_components_current_disconnected.html")
    generator._write_centered_html(fig1, path1)
    print(f"   ✅ Saved Map 1: {path1}")

    # -------------------------------------------------------------
    # MAP 2: POST SCENARIO (INTERVENED METROPOLITAN NETWORK + PROJECTS IN MAGENTA)
    # -------------------------------------------------------------
    print("   - [Map 2/2] Rendering Intervened Connected Scenario (Post Scenario)...")
    fig2 = go.Figure()
    bg_color2 = generator._add_osm_background(fig2, rec_gdf, green, water, build, limit, city_name="santiago", show_cycleways=False)

    # 1. Render neutral background for other secondary cycleways (Clusters 6 to 348)
    if not other_cycles.empty:
        fig2.add_trace(go.Scatter(
            x=xo, y=yo, mode='lines', name='Other Secondary Unconnected Cycleways',
            line=dict(color='#CFD8DC', width=1.0), connectgaps=False, hoverinfo='skip', showlegend=True
        ))

    # 2. Render Unconnected Component 2 (Sector Conchalí) in Purple (#763DF2)
    c2_edges = cycle_gdf[cycle_gdf['id'].isin([eid for eid, cid in edge_to_cluster.items() if cid == 2])]
    if not c2_edges.empty:
        xc2, yc2, hover2 = [], [], []
        for _, r in c2_edges.iterrows():
            h_text = f"<b>Unconnected Subnetwork (Cluster 2: Sector Conchalí)</b><br>Edge ID: {r['id']}"
            lines = [r.geometry] if r.geometry.geom_type == 'LineString' else list(r.geometry.geoms)
            for l in lines:
                xs, ys = l.xy
                xc2.extend(list(xs) + [None])
                yc2.extend(list(ys) + [None])
                hover2.extend([h_text] * (len(xs) + 1))

        fig2.add_trace(go.Scatter(
            x=xc2, y=yc2, mode='lines',
            name="Unconnected Subnetwork (Cluster 2: Sector Conchalí - 392 edges)",
            line=dict(color=palette[2], width=2.8), connectgaps=False, hoverinfo='text', text=hover2
        ))

    # 3. Render Intervened Metropolitan System (Clusters 1, 3, 4, 5 + 10 Projects) in Magenta (#F20574)
    intervened_cluster_ids = [1, 3, 4, 5]
    intervened_cycles = cycle_gdf[cycle_gdf['id'].isin([eid for eid, cid in edge_to_cluster.items() if cid in intervened_cluster_ids])]
    proj_gdf = rec_gdf[rec_gdf['is_project'] == True].copy()

    xm, ym, hover_m = [], [], []

    # Add pre-existing cycleways of Clusters 1, 3, 4, 5
    for _, r in intervened_cycles.iterrows():
        h_text = f"<b>Intervened Metropolitan System (Magenta)</b><br>Edge ID: {r['id']}"
        lines = [r.geometry] if r.geometry.geom_type == 'LineString' else list(r.geometry.geoms)
        for l in lines:
            xs, ys = l.xy
            xm.extend(list(xs) + [None])
            ym.extend(list(ys) + [None])
            hover_m.extend([h_text] * (len(xs) + 1))

    # Add the 10 new bikelane project corridors as part of the unified Magenta network
    if not proj_gdf.empty:
        for _, r in proj_gdf.iterrows():
            p_id = r.get('project_id', 'Project Corridor')
            flow_v = int(r.get('od_flow', 0) or 0)
            h_text = f"<b>Intervened Project Corridor: {p_id}</b><br>Flow: {flow_v} trips/day"
            lines = [r.geometry] if r.geometry.geom_type == 'LineString' else list(r.geometry.geoms)
            for l in lines:
                xs, ys = l.xy
                xm.extend(list(xs) + [None])
                ym.extend(list(ys) + [None])
                hover_m.extend([h_text] * (len(xs) + 1))

    fig2.add_trace(go.Scatter(
        x=xm, y=ym, mode='lines',
        name="Intervened Metropolitan Network (Clusters 1, 3, 4, 5 + 10 Projects)",
        line=dict(color=palette[1], width=3.0), connectgaps=False, hoverinfo='text', text=hover_m
    ))

    generator._apply_academic_layout(fig2, "Santiago Intervened Connected Metropolitan Scenario", x_range=[xmin, xmax], y_range=[ymin, ymax], bg_color=bg_color2)
    path2 = os.path.join(output_dir, "santiago_5_components_post_connected.html")
    generator._write_centered_html(fig2, path2)
    print(f"   ✅ Saved Map 2: {path2}")

    print("\n🎉 Both 5-Component Intervened Maps successfully generated!")

if __name__ == "__main__":
    main()
