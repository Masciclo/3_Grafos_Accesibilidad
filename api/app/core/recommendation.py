# +Ciclo: Generative Network Design & AI-Assisted Recommendation Engine 🚴‍♂️🤖

import os
import json
import time
import random
import math
import pandas as pd
import geopandas as gpd
from shapely import wkt
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

# Modular Imports
from core.metadata_agent import MetadataAgent, InteractiveGrillAgent, ProjectConfig
from core.overpass_client import OverpassClient
from infra.database import create_conn, execute_query
from infra.ingestion import create_abbreviation
from core.execution_logger import ExecutionLogger

console = Console()

class RecommendationEngine:
    def __init__(self, db_config: dict, data_base_path: str, city_key: str, srid: int):
        self.db_config = db_config
        self.data_base_path = data_base_path
        self.srid = srid
        
        # If city_key contains a comma, it's target_loc (osm_name)
        if "," in city_key:
            self.city_key = city_key.split(",")[0].strip().lower()
            self.net_prefix = create_abbreviation(city_key)
        else:
            self.city_key = city_key.strip().lower()
            if self.city_key == "valdivia":
                self.net_prefix = "valdchil"
            else:
                self.net_prefix = create_abbreviation(city_key)
        self.logger = None

    def _get_conn(self):
        return create_conn(
            self.db_config['name'],
            self.db_config['host'],
            self.db_config['port'],
            self.db_config['user'],
            self.db_config['password']
        )

    def run_recommendation_pipeline(self, prompt: str, reference_scenario: str, sample_size: int, study_area_bbox: list) -> str:
        """
        Orchestrates the entire generative cycleway optimization pipeline:
        1. Launches the interactive grilling session to collect project definitions.
        2. Geocodes seeds and parses design parameters using LLM subagents.
        3. Executes the custom cost-effective growth loop sequentially.
        4. Exports the consolidated upgraded network GeoJSON.
        """
        scenario_id = f"rec_{int(time.time())}"
        self.logger = ExecutionLogger(self.data_base_path, self.city_key, scenario_id)
        self.logger.set_phase("01_recommendation")
        self.logger.log(f"Initialized RecommendationEngine for city: {self.city_key}, scenario: {scenario_id}")

        console.print(Panel(
            "[bold green]🤖 INITIALIZING INTERACTIVE PROJECT GRILLING SESSION (+CICLO)[/]\n"
            "We will step-by-step define your bike lane expansion projects, custom growth algorithms, and locations.",
            title="Grilling Session", border_style="green"
        ))

        from core.telemetry import NetworkOntologyProfiler
        profiler = NetworkOntologyProfiler(self.db_config, self.net_prefix, reference_scenario)
        ontology_data = profiler.profile_city()

        grill_agent = InteractiveGrillAgent(ontology_data=ontology_data)
        grill_agent.render_city_diagnostic_panel()
        
        # Start grilling loop with a simple welcome message
        messages = [
            {"role": "user", "content": "Hello, let's start the grilling session to define projects."}
        ]
        
        project_config = None
        
        while True:
            # Call agent turn
            turn = grill_agent.grill_turn(messages)
            if turn.status == "COMPLETE" and turn.config:
                project_config = turn.config
                break
            else:
                # Print question in bold yellow
                console.print(f"\n[bold yellow]🤖 +Ciclo: {turn.next_question}[/]")
                user_reply = Prompt.ask("[bold green]You[/]")
                messages.append({"role": "model", "content": turn.next_question})
                messages.append({"role": "user", "content": user_reply})

        # Show consolidated preview panel
        while True:
            lambdas_str = ", ".join([f"{item.highway_type}: {item.multiplier}" for item in project_config.highway_lambdas]) if project_config.highway_lambdas else "None"
            
            console.print(Panel(
                f"[bold cyan]Proposed Parameters:[/]\n"
                f"• Requested Projects: [bold]{project_config.num_projects}[/]\n"
                f"• Length Budget: [bold]{project_config.budget_meters}m[/]\n"
                f"• Street Hierarchy Multipliers: [bold]{lambdas_str}[/]\n"
                f"• Destination/Gravity Attractor: [bold]{project_config.location_and_orientation.gravity_attractor or 'None'}[/]\n\n"
                f"[bold cyan]LLM-Interpreted Location:[/]\n"
                f"• Origin/Seed Target: [bold]{project_config.location_and_orientation.seed_target}[/]",
                title="Consolidated Project Configuration Summary", border_style="cyan"
            ))
            
            choice = Prompt.ask(
                "[bold yellow]Do you want to APPROVE this configuration? (Y: Approve/Yes, R: Refine with comments, N: Restart grilling)[/]",
                choices=["Y", "R", "N"], default="Y"
            ).upper()
            
            if choice == "Y":
                break
            elif choice == "R":
                feedback = Prompt.ask("[bold cyan]Enter your comments or desired modifications[/]")
                messages.append({"role": "user", "content": f"Feedback/Modifications: {feedback}"})
                while True:
                    turn = grill_agent.grill_turn(messages)
                    if turn.status == "COMPLETE" and turn.config:
                        project_config = turn.config
                        break
                    else:
                        console.print(f"\n[bold yellow]🤖 +Ciclo: {turn.next_question}[/]")
                        user_reply = Prompt.ask("[bold green]You[/]")
                        messages.append({"role": "model", "content": turn.next_question})
                        messages.append({"role": "user", "content": user_reply})
            else:
                # Restart grilling
                console.print("[bold red]Restarting grilling...[/]")
                messages = [
                    {"role": "user", "content": "Hello, let's start the grilling session to define projects."}
                ]
                while True:
                    turn = grill_agent.grill_turn(messages)
                    if turn.status == "COMPLETE" and turn.config:
                        project_config = turn.config
                        break
                    else:
                        console.print(f"\n[bold yellow]🤖 +Ciclo: {turn.next_question}[/]")
                        user_reply = Prompt.ask("[bold green]You[/]")
                        messages.append({"role": "model", "content": turn.next_question})
                        messages.append({"role": "user", "content": user_reply})

        # Resolve seeds only on approval
        console.print("[bold cyan]Resolving topological seeds in PostGIS...[/]")
        seed_edge_ids = self._resolve_project_seeds(project_config.location_and_orientation.seed_target, reference_scenario, study_area_bbox)
        if not seed_edge_ids:
            console.print("[bold red]Warning: Could not resolve any seeds in PostGIS. Using centrality-based fallback.[/]")
            seed_edge_ids = self._detect_growth_seeds(None, reference_scenario)
            
        projects_list = []
        # Support replicating config across the requested number of projects with distinct topological seeds
        for idx in range(project_config.num_projects):
            projects_list.append({
                "config": project_config,
                "seed_edge_ids": self._detect_growth_seeds(None, reference_scenario, offset=idx)
            })

        # Display final project table only if there are multiple projects
        if len(projects_list) > 1:
            table = Table(title="Approved Projects Descriptor Table")
            table.add_column("ID", style="cyan")
            table.add_column("Origin", style="magenta")
            table.add_column("Destination", style="green")
            table.add_column("Budget", style="yellow")
            table.add_column("Seeds (Edge IDs)", style="blue")
            
            for idx, proj in enumerate(projects_list):
                table.add_row(
                    f"P{idx+1}",
                    proj["config"].location_and_orientation.seed_target,
                    proj["config"].location_and_orientation.gravity_attractor or "None",
                    f"{proj['config'].budget_meters}m",
                    ", ".join(map(str, proj["seed_edge_ids"][:5])) + ("..." if len(proj["seed_edge_ids"]) > 5 else "")
                )
            console.print(table)

            # Final launch confirmation
            confirm = Prompt.ask("[bold yellow]Do you want to launch the consolidated simulation with all these projects? (Y/N)[/]", choices=["Y", "N"], default="Y").upper()
            if confirm == "N":
                console.print("[bold red]Simulation cancelled by user.[/]")
                return ""

        # Solve greedy growth sequentially for each approved project (Cumulative Growth)
        all_upgrades = []
        accumulated_upgrades = set()
        for idx, proj in enumerate(projects_list):
            config = proj["config"]
            seeds = proj["seed_edge_ids"]
            lambdas_dict = {item.highway_type: item.multiplier for item in config.highway_lambdas} if config.highway_lambdas else {}
            console.print(f"\n[bold green]⚙️ Running optimization for project {idx+1}: Connector {config.location_and_orientation.seed_target}...[/]")
            selected = self._solve_greedy_growth(
                seed_edge_ids=seeds,
                reference_scenario=reference_scenario,
                budget=config.budget_meters,
                sample_size=sample_size,
                highway_lambdas=lambdas_dict,
                gravity_attractor=config.location_and_orientation.gravity_attractor,
                study_area_bbox=study_area_bbox,
                accumulated_upgrades=accumulated_upgrades
            )
            proj["selected_edges"] = selected
            all_upgrades.extend(selected)
            accumulated_upgrades.update(selected)

        # Deduplicate
        all_upgrades = list(set(all_upgrades))

        if not all_upgrades:
            console.print("[bold red]Optimization did not produce any improvement segments.[/]")
            return ""

        # Export unified GeoJSON
        console.print("\n[bold green]💾 Exporting unified GeoJSON file...[/]")
        rec_geojson_path = self._export_geojson(projects_list, reference_scenario)
        return rec_geojson_path

    def _resolve_project_seeds(self, seed_target: str, reference_scenario: str, study_area_bbox: list) -> list[int]:
        net_table = f"{self.net_prefix}_{reference_scenario}_internal_net"
        conn = self._get_conn()
        cur = conn.cursor()
        
        seed_edge_ids = []
        
        try:
            if seed_target:
                poi_path = os.path.join(self.data_base_path, self.city_key, "proc", "toponymy", "poi_temp_seed.geojson")
                query = f"""
                [out:json][timeout:25][bbox:{{bbox}}];
                (
                  node["name"~"{seed_target}",i];
                  way["name"~"{seed_target}",i];
                );
                out center;
                """
                client = OverpassClient()
                if client.download_pois(query, study_area_bbox, poi_path):
                    gdf = gpd.read_file(poi_path)
                    if not gdf.empty:
                        centroid = gdf.geometry.unary_union.centroid
                        
                        # Find the highest-flow street segment within 500m of the centroid
                        cur.execute(f"""
                            SELECT id 
                            FROM {net_table}
                            WHERE highway != 'cycleway'
                              AND highway NOT IN ('motorway', 'trunk')
                              AND ST_DWithin(ST_Transform(geometry, {self.srid}), ST_Transform(ST_SetSRID(ST_Point(%s, %s), 4326), {self.srid}), 500)
                            ORDER BY COALESCE(od_flow, 0) DESC
                            LIMIT 1;
                        """, (centroid.x, centroid.y))
                        row = cur.fetchone()
                        
                        # Fallback: if no street is within 500m, search up to 1500m
                        if not row:
                            cur.execute(f"""
                                SELECT id 
                                FROM {net_table}
                                WHERE highway != 'cycleway'
                                  AND highway NOT IN ('motorway', 'trunk')
                                  AND ST_DWithin(ST_Transform(geometry, {self.srid}), ST_Transform(ST_SetSRID(ST_Point(%s, %s), 4326), {self.srid}), 1500)
                                ORDER BY COALESCE(od_flow, 0) DESC
                                LIMIT 1;
                            """, (centroid.x, centroid.y))
                            row = cur.fetchone()
                            
                        # Double Fallback: if still none, pick the single closest street edge (any distance)
                        if not row:
                            cur.execute(f"""
                                SELECT id 
                                FROM {net_table}
                                WHERE highway != 'cycleway'
                                ORDER BY geometry <-> ST_SetSRID(ST_Point(%s, %s), 4326)
                                LIMIT 1;
                            """, (centroid.x, centroid.y))
                            row = cur.fetchone()
                            
                        if row:
                            seed_edge_ids = [row[0]]
            
            if not seed_edge_ids:
                seed_edge_ids = self._detect_growth_seeds(None, reference_scenario)
                
        except Exception as e:
            console.print(f"[Warning] Error resolving topological seeds: {e}. Falling back to centrality.")
            seed_edge_ids = self._detect_growth_seeds(None, reference_scenario)
        finally:
            cur.close()
            conn.close()
            
        return seed_edge_ids

    def _detect_growth_seeds(self, poi_path: str, reference_scenario: str, offset: int = 0) -> list[int]:
        """
        Groups cycleways into components, selects the component with the highest baseline flow,
        and then finds the highest-flow street segment within 500 meters of that component (offset by rank).
        """
        net_table = f"{self.net_prefix}_{reference_scenario}_internal_net"
        conn = self._get_conn()
        cur = conn.cursor()

        # Step A: Get all existing cycleway edges in reference scenario along with their baseline flow
        cur.execute(f"""
            SELECT id, source, target, ST_AsText(geometry), COALESCE(od_flow, 0) as base_flow
            FROM {net_table} 
            WHERE highway = 'cycleway' AND is_project = FALSE;
        """)
        cycleway_rows = cur.fetchall()

        if not cycleway_rows:
            # Fallback: if no cycleway exists, pick the segment with highest latent demand to start a new network
            console.print("[bold yellow]No existing cycleway edges found. Selecting highest latent demand segment as seed...[/]")
            base_table = f"{self.net_prefix}_baseline_internal_net"
            cur.execute(f"""
                SELECT curr.id 
                FROM {net_table} curr
                JOIN {base_table} base ON curr.id = base.id
                WHERE curr.highway != 'cycleway'
                  AND curr.highway NOT IN ('motorway', 'trunk')
                ORDER BY (COALESCE(base.od_flow, 0) - COALESCE(curr.od_flow, 0)) DESC
                LIMIT 1 OFFSET %s;
            """, (offset,))
            fallback = cur.fetchone()
            cur.close()
            conn.close()
            return [fallback[0]] if fallback else []

        # Step B: Build topological components (adjacency list search)
        adj = {}
        edge_to_nodes = {}
        edge_flows = {}
        for r in cycleway_rows:
            eid, src, tgt, _, flow = r
            edge_to_nodes[eid] = (src, tgt)
            edge_flows[eid] = float(flow)
            adj.setdefault(src, []).append(eid)
            adj.setdefault(tgt, []).append(eid)

        visited_edges = set()
        components = []

        for r in cycleway_rows:
            eid = r[0]
            if eid in visited_edges:
                continue
            # BFS to find component
            comp = []
            queue = [eid]
            visited_edges.add(eid)
            while queue:
                curr_eid = queue.pop(0)
                comp.append(curr_eid)
                src, tgt = edge_to_nodes[curr_eid]
                # Find connected edges
                for next_eid in adj.get(src, []) + adj.get(tgt, []):
                    if next_eid not in visited_edges:
                        visited_edges.add(next_eid)
                        queue.append(next_eid)
            components.append(comp)

        # Compute total baseline flow and edge count for each component
        component_stats = []
        for i, comp in enumerate(components):
            comp_flow = sum(edge_flows.get(eid, 0.0) for eid in comp)
            component_stats.append((comp, comp_flow, len(comp)))

        # Sort components by total baseline flow descending
        component_stats.sort(key=lambda x: x[1], reverse=True)

        if offset == 0:
            console.print(f"Detected [bold]{len(components)}[/] disconnected cycleway clusters in reference scenario.")
            console.print("[bold cyan]Top 5 cycleway clusters sorted by baseline flow:[/]")
            for idx, (comp, flow, size) in enumerate(component_stats[:5]):
                console.print(f"  - Cluster {idx+1}: {size} edges, Total Flow: {round(flow, 1)} active trips/day (Example Edge ID: {comp[0]})")

        # Automatically select the highest flow component as the seed X_seed
        selected_component = component_stats[0][0]

        # Find the highest-flow street segment within 500m of the selected component's geometries (offset by project index)
        selected_edge_ids_str = ",".join(map(str, selected_component))
        cur.execute(f"""
            SELECT s.id, COALESCE(s.od_flow, 0) as flow
            FROM {net_table} s
            WHERE s.highway != 'cycleway'
              AND s.highway NOT IN ('motorway', 'trunk')
              AND EXISTS (
                  SELECT 1 FROM {net_table} c
                  WHERE c.id IN ({selected_edge_ids_str})
                    AND ST_DWithin(ST_Transform(s.geometry, {self.srid}), ST_Transform(c.geometry, {self.srid}), 500)
              )
            ORDER BY COALESCE(s.od_flow, 0) DESC
            LIMIT 1 OFFSET %s;
        """, (offset,))
        row = cur.fetchone()

        if row:
            starting_edge_id = row[0]
            starting_flow = row[1]
            console.print(f"  - [Project Seed Rank #{offset+1}] Spawning on adjacent high-flow street segment: ID {starting_edge_id} (Flow: {round(starting_flow, 1)} trips/day)")
        else:
            # Fallback to the highest flow edge inside the cycleway cluster itself if no adjacent streets found
            selected_component.sort(key=lambda eid: edge_flows.get(eid, 0.0), reverse=True)
            starting_edge_id = selected_component[min(offset, len(selected_component)-1)]
            console.print(f"  - [Fallback Rank #{offset+1}] Spawning inside cluster itself: ID {starting_edge_id} (Flow: {round(edge_flows.get(starting_edge_id, 0.0), 1)} trips/day)")

        cur.close()
        conn.close()
        return [starting_edge_id]

    def _topological_lookahead_compass(self, cur, cand_id: int, max_depth: int, net_table: str, active_nodes_str: str) -> tuple[float, float, float]:
        """
        Executes a recursive SQL CTE representing a BFS look-ahead up to max_depth hops.
        Returns:
            total_flow: cumulative latent demand flow in the branch.
            end_x: X coordinate of the centroid of reached edges.
            end_y: Y coordinate of the centroid of reached edges.
        """
        cur.execute(f"""
            WITH RECURSIVE bfs_tree(edge_id, node, depth, path) AS (
                SELECT 
                    id, 
                    CASE WHEN source IN ({active_nodes_str}) THEN target ELSE source END, 
                    1, 
                    ARRAY[source, target]
                FROM {net_table}
                WHERE id = %s
                
                UNION ALL
                
                SELECT 
                    n.id,
                    CASE WHEN n.source = t.node THEN n.target ELSE n.source END,
                    t.depth + 1,
                    t.path || CASE WHEN n.source = t.node THEN n.target ELSE n.source END
                FROM {net_table} n
                JOIN bfs_tree t ON (n.source = t.node OR n.target = t.node)
                WHERE t.depth < %s
                  AND NOT (CASE WHEN n.source = t.node THEN n.target ELSE n.source END = ANY(t.path))
            )
            SELECT 
                COALESCE(SUM(COALESCE(od_flow, 0)), 0) as total_flow,
                ST_X(ST_Centroid(ST_Union(geometry))) as end_x,
                ST_Y(ST_Centroid(ST_Union(geometry))) as end_y
            FROM {net_table}
            WHERE id IN (SELECT DISTINCT edge_id FROM bfs_tree);
        """, (cand_id, max_depth))
        
        row = cur.fetchone()
        if row and row[1] is not None and row[2] is not None:
            return float(row[0]), float(row[1]), float(row[2])
        return 0.0, 0.0, 0.0

    def _solve_greedy_growth(self, seed_edge_ids: list[int], reference_scenario: str, budget: float, sample_size: int, highway_lambdas: dict = None, gravity_attractor: str = None, study_area_bbox: list = None, accumulated_upgrades: set[int] = None) -> list[int]:
        """
        Executes the greedy selection loop using Cost-Effectiveness Ratio (CER) and Uniform Sampling (BUS).
        Supports Cumulative Greedy Growth by recognizing accumulated_upgrades as built bikelanes and latch points.
        """
        net_table = f"{self.net_prefix}_{reference_scenario}_internal_net"
        conn = self._get_conn()
        cur = conn.cursor()

        # Step A: Load Travel Demand Pairs to draw samples from
        cur.execute(f"""
            SELECT 
                o.node_id as origin_node, 
                d.node_id as dest_node, 
                SUM(m.trips) as od_flow
            FROM {self.net_prefix}_{reference_scenario}_od_matrix m
            JOIN {self.net_prefix}_{reference_scenario}_h3_to_node o ON m.h3_origin = o.h3_index
            JOIN {self.net_prefix}_{reference_scenario}_h3_to_node d ON m.h3_dest = d.h3_index
            WHERE m.trips > 0
            GROUP BY o.node_id, d.node_id
            ORDER BY od_flow DESC;
        """)
        demand_rows = cur.fetchall()
        if not demand_rows:
            console.print("[bold red]Error: No H3 demand matrix entries found in database.[/]")
            cur.close()
            conn.close()
            return []

        # Draw a uniform sample Q of size sample_size (weighted by flow sizes)
        population_pairs = []
        for r in demand_rows:
            population_pairs.append((r[0], r[1], float(r[2])))
            
        # Adaptive sample size guard for large networks (prevents PostgreSQL OOM crashes on Santiago/Valparaiso)
        max_safe_sample = 100 if len(population_pairs) > 50000 else 500
        sample_size = min(sample_size, len(population_pairs), max_safe_sample)
        Q = random.sample(population_pairs, sample_size)
        console.print(f"Sampled [bold]{len(Q)}[/] active OD pairs for BUS evaluation (from total {len(population_pairs)} active pairs).")

        active_edges = set(seed_edge_ids)
        acc_edges = set(accumulated_upgrades) if accumulated_upgrades else set()
        budget_remaining = budget
        selected_upgrades = []

        seed_edge_id = seed_edge_ids[0]
        
        # Get source and target of starting seed to initialize active leaf nodes
        cur.execute(f"SELECT source, target FROM {net_table} WHERE id = %s", (seed_edge_id,))
        seed_src, seed_tgt = cur.fetchone()
        active_nodes = {seed_src, seed_tgt}

        # If accumulated projects exist, register their node endpoints as active latch points
        if acc_edges:
            acc_ids_tmp = ",".join(map(str, acc_edges))
            cur.execute(f"SELECT DISTINCT source, target FROM {net_table} WHERE id IN ({acc_ids_tmp})")
            for acc_s, acc_t in cur.fetchall():
                active_nodes.add(acc_s)
                active_nodes.add(acc_t)

        origins = [p[0] for p in Q]
        destinations = [p[1] for p in Q]
        
        # Query seed's centroid
        cur.execute(f"SELECT ST_X(ST_Centroid(geometry)), ST_Y(ST_Centroid(geometry)) FROM {net_table} WHERE id = %s", (seed_edge_id,))
        seed_x, seed_y = cur.fetchone()
        last_x, last_y = seed_x, seed_y

        # Geocode gravity attractor point if needed
        attractor_pt = None
        if gravity_attractor and study_area_bbox:
            try:
                poi_path = os.path.join(self.data_base_path, self.city_key, "proc", "toponymy", "attractor_temp.geojson")
                agent = MetadataAgent()
                query = agent.generate_overpass_query([], [gravity_attractor])
                client = OverpassClient()
                if client.download_pois(query, study_area_bbox, poi_path):
                    gdf = gpd.read_file(poi_path)
                    if not gdf.empty:
                        attractor_pt = gdf.geometry.unary_union.centroid
            except Exception as e:
                console.print(f"[Warning] Could not resolve gravity attractor: {e}")
        
        # Greedy loop
        iteration = 1
        while budget_remaining > 0:
            console.print(f"\n[bold yellow]--- Iteration {iteration} (Budget Remaining: {round(budget_remaining, 1)}m) ---[/]")
            
            # If budget is too low to build any realistic new street segment, disable free cycleway stitching to force termination
            allow_free_stitching = (budget_remaining >= 15.0)
            
            # Compute v_target
            if attractor_pt:
                v_target = (attractor_pt.x - last_x, attractor_pt.y - last_y)
            else:
                v_target = (last_x - seed_x, last_y - seed_y)
            
            active_nodes_str = ",".join(map(str, active_nodes))
            all_built_edges = active_edges.union(acc_edges)
            active_ids_str = ",".join(map(str, all_built_edges))
            
            # Query candidates adjacent ONLY to the active endpoints of our single continuous path
            cur.execute(f"""
                SELECT id, ST_Length(geometry) as length, highway, ST_AsText(geometry), COALESCE(od_flow, 0) as base_flow, source, target
                FROM {net_table}
                WHERE id NOT IN ({active_ids_str})
                  AND (
                      source IN ({active_nodes_str}) OR target IN ({active_nodes_str})
                  )
                ORDER BY COALESCE(od_flow, 0) DESC
                LIMIT 150;
            """)
            candidates = cur.fetchall()

            if not candidates:
                console.print("[bold yellow]No more topologically adjacent candidates within length limits. Terminating loop.[/]")
                break

            best_candidate = None
            best_cer = 0.0
            best_length = 0.0
            best_highway = ""
            best_src = None
            best_tgt = None

            best_fallback_candidate = None
            best_fallback_cer = 0.0
            best_fallback_length = 0.0
            best_fallback_highway = ""
            best_fallback_src = None
            best_fallback_tgt = None

            # Progress Bar for candidate evaluations
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                console=console
            ) as progress:
                task = progress.add_task(f"Evaluating {len(candidates)} candidates...", total=len(candidates))
                
                for cand in candidates:
                    cand_id, cand_len, cand_highway, cand_wkt, base_flow, src_node, tgt_node = cand
                    
                    cur.execute(f"""
                        SELECT COUNT(DISTINCT (start_vid, end_vid)) as captured_pairs
                        FROM pgr_dijkstra(
                            'SELECT id, source, target, 
                                     CASE WHEN id = {cand_id} THEN length * 0.5 
                                          WHEN id IN ({active_ids_str}) THEN length * 0.5
                                          ELSE cost 
                                     END as cost 
                              FROM {net_table}',
                            %s,
                            %s,
                            directed := true
                        )
                        WHERE edge = {cand_id};
                    """, (origins, destinations))
                    
                    captured_count = cur.fetchone()[0]
                    
                    # Network Stitching Cost: zero-cost if already a cycleway
                    if cand_highway == 'cycleway':
                        if not allow_free_stitching:
                            progress.update(task, advance=1)
                            continue
                        cost_factor = 0.0
                    else:
                        cost_factor = highway_lambdas.get(cand_highway, 1.0) if highway_lambdas else 1.0
                    adjusted_len = float(cand_len) * cost_factor
                    
                    # Apply gravity attractor
                    gravity_multiplier = 1.0
                    if attractor_pt:
                        try:
                            cur.execute("""
                                SELECT ST_Distance(
                                    ST_Transform(ST_GeomFromText(%s, 4326), 32718),
                                    ST_Transform(ST_SetSRID(ST_Point(%s, %s), 4326), 32718)
                                );
                            """, (cand_wkt, attractor_pt.x, attractor_pt.y))
                            dist_meters = cur.fetchone()[0]
                            gravity_multiplier = math.exp(-0.0005 * dist_meters)
                        except Exception:
                            pass

                    # Topological Search Compass: look-ahead H=3, adaptive to H=5
                    topological_multiplier = 1.0
                    try:
                        look_flow, _, _ = self._topological_lookahead_compass(cur, cand_id, 3, net_table, active_nodes_str)
                        # Adaptive depth
                        if look_flow < 1000.0:
                            look_flow, _, _ = self._topological_lookahead_compass(cur, cand_id, 5, net_table, active_nodes_str)
                        
                        topological_multiplier = math.log10(look_flow + 10.0)
                    except Exception:
                        pass

                    # Budget Overrun Penalty Multiplier (TS78)
                    if adjusted_len > budget_remaining and budget_remaining > 0:
                        budget_penalty = budget_remaining / adjusted_len
                    else:
                        budget_penalty = 1.0

                    cer = ((float(captured_count) * gravity_multiplier * topological_multiplier) / (adjusted_len + 30.0)) * budget_penalty
                    fallback_cer = ((max(float(base_flow), 1e-5) * gravity_multiplier * topological_multiplier) / (adjusted_len + 30.0)) * budget_penalty
                    
                    if cer > best_cer:
                        best_cer = cer
                        best_candidate = cand_id
                        best_length = cand_len
                        best_highway = cand_highway
                        best_src = src_node
                        best_tgt = tgt_node
                        
                    if fallback_cer > best_fallback_cer:
                        best_fallback_cer = fallback_cer
                        best_fallback_candidate = cand_id
                        best_fallback_length = cand_len
                        best_fallback_highway = cand_highway
                        best_fallback_src = src_node
                        best_fallback_tgt = tgt_node
                        
                    progress.update(task, advance=1)

            if best_candidate is None and best_fallback_candidate is not None:
                best_candidate = best_fallback_candidate
                best_length = best_fallback_length
                best_cer = best_fallback_cer
                best_highway = best_fallback_highway
                best_src = best_fallback_src
                best_tgt = best_fallback_tgt
                console.print(f"[dim]Using baseline flow fallback for expansion (CER: {round(best_cer, 5)})[/]")

            if best_candidate is None:
                console.print("[bold yellow]No beneficial candidates found. Terminating loop.[/]")
                break

            active_edges.add(best_candidate)
            selected_upgrades.append(best_candidate)
            
            # Update active endpoints to maintain a single continuous corridor path (no branching)
            if best_src in active_nodes and best_tgt in active_nodes:
                active_nodes.remove(best_src)
                active_nodes.remove(best_tgt)
            elif best_src in active_nodes:
                active_nodes.remove(best_src)
                active_nodes.add(best_tgt)
            elif best_tgt in active_nodes:
                active_nodes.remove(best_tgt)
                active_nodes.add(best_src)
            
            # Subtract budget using actual cost factor
            cost_factor = 0.0 if best_highway == 'cycleway' else (highway_lambdas.get(best_highway, 1.0) if highway_lambdas else 1.0)
            budget_cost = best_length * cost_factor
            budget_remaining -= budget_cost
            
            # Update last coordinate to track trajectory
            try:
                cur.execute(f"SELECT ST_X(ST_Centroid(geometry)), ST_Y(ST_Centroid(geometry)) FROM {net_table} WHERE id = %s", (best_candidate,))
                last_x, last_y = cur.fetchone()
            except Exception:
                pass
            
            # Informative print regarding budget vs physical length
            log_msg = f"Iteration {iteration}: Selected Edge ID {best_candidate} (Length: {round(best_length, 1)}m, Budget Cost: {round(budget_cost, 1)}m, CER: {round(best_cer, 5)})"
            if self.logger:
                self.logger.log(log_msg)

            if budget_cost == 0.0:
                console.print(f"🎉 Selected Edge ID [bold]{best_candidate}[/] (Length: {round(best_length, 1)}m, [green]Stitched Free Cycleway[/], CER: {round(best_cer, 5)})")
            elif budget_remaining < 0.0:
                console.print(f"🎉 Selected Edge ID [bold]{best_candidate}[/] (Length: {round(best_length, 1)}m, [red]Final Over-budget Segment[/] cost: {round(budget_cost, 1)}m, CER: {round(best_cer, 5)})")
            else:
                console.print(f"🎉 Selected Edge ID [bold]{best_candidate}[/] (Length: {round(best_length, 1)}m, Budget Cost: {round(budget_cost, 1)}m, CER: {round(best_cer, 5)})")
            iteration += 1

        cur.close()
        conn.close()
        return selected_upgrades

    def _export_geojson(self, projects_list: list[dict], reference_scenario: str) -> str:
        """
        Retrieves geometry features for the selected upgraded edges and writes them to a GeoJSON file.
        """
        net_table = f"{self.net_prefix}_{reference_scenario}_internal_net"
        conn = self._get_conn()
        cur = conn.cursor()

        features = []
        for idx, proj in enumerate(projects_list):
            edge_ids = proj.get("selected_edges", [])
            if not edge_ids:
                continue
            edge_ids_str = ",".join(map(str, edge_ids))
            cur.execute(f"""
                SELECT id, highway, ST_AsText(ST_Transform(geometry, 4326)) as geom_wkt
                FROM {net_table}
                WHERE id IN ({edge_ids_str}) AND highway != 'cycleway';
            """)
            rows = cur.fetchall()
            for r in rows:
                eid, hway, geom_str = r
                shape = wkt.loads(geom_str)
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": list(shape.coords)
                    },
                    "properties": {
                        "project_id": f"rec_{idx+1}",
                        "highway_original": hway,
                        "is_recommendation": True,
                        "parent_baseline_id": eid
                    }
                }
                features.append(feature)

        cur.close()
        conn.close()

        geojson = {
            "type": "FeatureCollection",
            "features": features
        }

        timestamp = int(time.time())
        output_dir = os.path.join(self.data_base_path, self.city_key, "proc", "projects")
        os.makedirs(output_dir, exist_ok=True)
        geojson_path = os.path.join(output_dir, f"recommendation_{timestamp}.geojson")

        with open(geojson_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)

        return geojson_path
