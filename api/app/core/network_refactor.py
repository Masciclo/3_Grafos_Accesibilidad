import os
from typing import Dict, Any, Optional, List, Protocol
from dataclasses import dataclass, field
from core.pipeline import ScenarioConfig, ProgressSeam
from infra.database import execute_query, read_sql_file
from infra.schema import SchemaGuard
from infra.ingestion import create_abbreviation
from ui.components import diagnostic_handler

@dataclass(frozen=True)
class NetworkGraphRef:
    """
    Represents a reference to a spatial-topological network database state.
    """
    connection: Any
    osm_table: str
    ciclo_table: str
    net_table: str
    srid: int

@dataclass(frozen=True)
class ProjectLayer:
    """
    Encapsulates a logical layer of proposed infrastructure interventions.
    """
    layer_id: str
    projects_table: str
    ref_snap_dist: float = 5.0
    project_influence_dist: float = 25.0
    cycleway_impedance: float = 0.5

@dataclass(frozen=True)
class RefactorContext:
    """
    Parameters, paths, and observer references for the refactoring execution.
    """
    scenario_id: str
    location: str
    sql_base_path: str
    observer: Optional[ProgressSeam] = None
    buffer_size: float = 15.0
    disinhibit: bool = True
    imp_primary: float = 10.0
    imp_secondary: float = 5.0
    imp_tertiary: float = 3.0
    imp_local: float = 1.0
    imp_bike: float = 0.5

@dataclass(frozen=True)
class RefactorResult:
    """
    Encapsulates the resulting output table names of the refactored network.
    """
    scenery_table: str
    internal_net_table: str
    diagnostic_tables: Dict[str, str] = field(default_factory=dict)

class RefactorStrategy(Protocol):
    """
    Polymorphic seam for executing network refactoring workflows.
    """
    def refactor(
        self, 
        base_network: NetworkGraphRef, 
        layers: List[ProjectLayer], 
        context: RefactorContext
    ) -> RefactorResult:
        ...


class TrivialIdentityStrategy:
    """
    Equal Topology Scenario strategy (V0/V1 baseline).
    Bypasses spatial edits and snapping, only executing safety-impedance calculations.
    """
    def refactor(
        self, 
        base_network: NetworkGraphRef, 
        layers: List[ProjectLayer], 
        context: RefactorContext
    ) -> RefactorResult:
        conn = base_network.connection
        if context.observer:
            context.observer.on_progress_update("Refactorización de la Topología", increment=1)

        location_prefix = create_abbreviation(context.location)
        scenery_name = f"{location_prefix}_{context.scenario_id}_osm_proc"
        
        osm_table = base_network.osm_table
        internal_net_table = base_network.net_table
        ciclo_table = base_network.ciclo_table

        # 1. High-Fidelity Invariant Prep
        SchemaGuard.ensure_network_parity(conn, osm_table)

        # 2. INHIBITION (Impedance Surface)
        if context.observer:
            context.observer.on_progress_update("Refactorización de la Topología", increment=1)

        execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'create_impedance_buffers.sql')).format(
            result_table=f'{scenery_name}_imp_buff', 
            table_name=osm_table, 
            dist_buffer=context.buffer_size, 
            high_impedance=context.imp_primary, 
            medium_impedance=context.imp_secondary, 
            low_impedance=context.imp_tertiary, 
            else_impedance=context.imp_local
        ))

        use_buffer = f'{scenery_name}_imp_buff'
        if context.disinhibit:
            if context.observer:
                context.observer.report_diagnostic("DISINHIBITION", "INFO", "Executing cycleway desinhibition buffer subtraction...")
            
            des_lines = f'{scenery_name}_desinhibitor_lines'
            execute_query(conn, f"DROP TABLE IF EXISTS public.{des_lines};")
            execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'union_desinhibit.sql')).format(
                desinhibitor_name=des_lines,
                ciclo_table=ciclo_table,
                desinhibitor_table=ciclo_table,
                filters=""
            ))
            
            des_buff = f'{scenery_name}_desinhibitor_buff'
            execute_query(conn, f"DROP TABLE IF EXISTS buffers.{des_buff};")
            execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'create_buffer.sql')).format(
                result_table=des_buff,
                table_name=f"public.{des_lines}",
                dist_buffer=context.buffer_size
            ))
            
            imp_diff = f'{scenery_name}_imp_diff'
            execute_query(conn, f"DROP TABLE IF EXISTS buffers.{imp_diff};")
            execute_query(conn, f"DROP TABLE IF EXISTS buffers.{scenery_name}_inhib_diff;")
            execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'buffer_difference.sql')).format(
                inhib_name=f'{scenery_name}_inhib_diff',
                buffer_inhibitor=f'{scenery_name}_imp_buff',
                buffer_desinhibitor=des_buff,
                impedance_name=imp_diff,
                buffer_impedance=f'{scenery_name}_imp_buff'
            ))
            use_buffer = imp_diff

        execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'create_inhibited_network.sql')).format(
            result_name=scenery_name, 
            network_table=osm_table, 
            inhib_buffer=use_buffer, 
            impedance_buffer=use_buffer
        ))

        # 3. MERGING
        execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'create_full_network.sql')).format(
            result_name=internal_net_table, 
            ciclo=ciclo_table, 
            osm=scenery_name, 
            filters="", 
            bike_impedance=context.imp_bike,
            projects_union=""
        ))

        # 4. FINAL TOPOLOGICAL REPAIR
        if context.observer:
            context.observer.report_diagnostic("TOPOLOGY_FINAL", "INFO", "Building final routing topology...")
            
        execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'create_routing_topology.sql')).format(
            table=internal_net_table, 
            tolerance=0.1
        ))

        # 5. Snap Baseline Cycleways (Welding)
        _weld_cycleways(conn, internal_net_table, context.observer)

        # 6. Final Graph Cleaning
        execute_query(conn, f"DELETE FROM {internal_net_table} WHERE ST_Length(geometry) < 0.5;")

        return RefactorResult(scenery_table=scenery_name, internal_net_table=internal_net_table)


class RecommendationStrategy:
    """
    Algorithmic Discovery scenario strategy.
    Bypasses Python-level spatial refactoring, unioning recommended corridors directly in Stage 2.
    """
    def refactor(
        self, 
        base_network: NetworkGraphRef, 
        layers: List[ProjectLayer], 
        context: RefactorContext
    ) -> RefactorResult:
        conn = base_network.connection
        if context.observer:
            context.observer.on_progress_update("Refactorización de la Topología", increment=1)

        location_prefix = create_abbreviation(context.location)
        scenery_name = f"{location_prefix}_{context.scenario_id}_osm_proc"
        
        osm_table = base_network.osm_table
        internal_net_table = base_network.net_table
        ciclo_table = base_network.ciclo_table
        
        # We assume exactly one project layer for recommended geometries
        layer = layers[0]
        projects_table = layer.projects_table

        # 1. High-Fidelity Invariant Prep
        SchemaGuard.ensure_network_parity(conn, osm_table)

        # 2. INHIBITION (Impedance Surface)
        if context.observer:
            context.observer.on_progress_update("Refactorización de la Topología", increment=1)

        execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'create_impedance_buffers.sql')).format(
            result_table=f'{scenery_name}_imp_buff', 
            table_name=osm_table, 
            dist_buffer=context.buffer_size, 
            high_impedance=context.imp_primary, 
            medium_impedance=context.imp_secondary, 
            low_impedance=context.imp_tertiary, 
            else_impedance=context.imp_local
        ))

        use_buffer = f'{scenery_name}_imp_buff'
        if context.disinhibit:
            if context.observer:
                context.observer.report_diagnostic("DISINHIBITION", "INFO", "Executing cycleway desinhibition buffer subtraction...")
            
            des_lines = f'{scenery_name}_desinhibitor_lines'
            execute_query(conn, f"DROP TABLE IF EXISTS public.{des_lines};")
            execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'union_desinhibit.sql')).format(
                desinhibitor_name=des_lines,
                ciclo_table=ciclo_table,
                desinhibitor_table=projects_table,
                filters=""
            ))
            
            des_buff = f'{scenery_name}_desinhibitor_buff'
            execute_query(conn, f"DROP TABLE IF EXISTS buffers.{des_buff};")
            execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'create_buffer.sql')).format(
                result_table=des_buff,
                table_name=f"public.{des_lines}",
                dist_buffer=context.buffer_size
            ))
            
            imp_diff = f'{scenery_name}_imp_diff'
            execute_query(conn, f"DROP TABLE IF EXISTS buffers.{imp_diff};")
            execute_query(conn, f"DROP TABLE IF EXISTS buffers.{scenery_name}_inhib_diff;")
            execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'buffer_difference.sql')).format(
                inhib_name=f'{scenery_name}_inhib_diff',
                buffer_inhibitor=f'{scenery_name}_imp_buff',
                buffer_desinhibitor=des_buff,
                impedance_name=imp_diff,
                buffer_impedance=f'{scenery_name}_imp_buff'
            ))
            use_buffer = imp_diff

        execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'create_inhibited_network.sql')).format(
            result_name=scenery_name, 
            network_table=osm_table, 
            inhib_buffer=use_buffer, 
            impedance_buffer=use_buffer
        ))

        # 3. MERGING (Dynamic SQL Union)
        if context.observer:
            context.observer.report_diagnostic("REFACTOR", "INFO", "Recommendation project detected. Bypassing spatial suturing...")

        projects_union = f"""
        UNION ALL
        SELECT 
            (ST_Dump(ST_MakeValid(geometry))).geom as geometry,
            {context.imp_bike}::float as impedance,
            'cycleway'::text as highway,
            'cycleway'::text as original_highway,
            TRUE as is_project,
            project_id::text as project_id,
            parent_baseline_id::integer as parent_baseline_id
        FROM {projects_table}
        WHERE geometry IS NOT NULL
        """

        execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'create_full_network.sql')).format(
            result_name=internal_net_table, 
            ciclo=ciclo_table, 
            osm=scenery_name, 
            filters="", 
            bike_impedance=context.imp_bike,
            projects_union=projects_union
        ))

        # 4. FINAL TOPOLOGICAL REPAIR
        if context.observer:
            context.observer.report_diagnostic("TOPOLOGY_FINAL", "INFO", "Building final routing topology...")
            
        execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'create_routing_topology.sql')).format(
            table=internal_net_table, 
            tolerance=0.1
        ))

        # 5. Snap Baseline Cycleways (Welding)
        _weld_cycleways(conn, internal_net_table, context.observer)

        # 6. Final Graph Cleaning
        execute_query(conn, f"DELETE FROM {internal_net_table} WHERE ST_Length(geometry) < 0.5;")

        return RefactorResult(scenery_table=scenery_name, internal_net_table=internal_net_table)


class SuturaRefactorStrategy:
    """
    Manual Drawing scenario strategy.
    Performs spatial snapping, shattering, conflict resolution, and endpoint plugging in PostGIS.
    """
    def refactor(
        self, 
        base_network: NetworkGraphRef, 
        layers: List[ProjectLayer], 
        context: RefactorContext
    ) -> RefactorResult:
        conn = base_network.connection
        if context.observer:
            context.observer.on_progress_update("Refactorización de la Topología", increment=1)

        location_prefix = create_abbreviation(context.location)
        scenery_name = f"{location_prefix}_{context.scenario_id}_osm_proc"
        
        osm_table = base_network.osm_table
        internal_net_table = base_network.net_table
        ciclo_table = base_network.ciclo_table
        
        layer = layers[0]
        projects_table = layer.projects_table
        mr_dist = layer.ref_snap_dist
        zp_dist = layer.project_influence_dist

        # 1. High-Fidelity Invariant Prep
        SchemaGuard.ensure_network_parity(conn, osm_table)

        # 2. ASSIMILATIVE REFACTORING
        if context.observer:
            context.observer.report_diagnostic("REFACTOR", "INFO", f"Executing Adaptive Suturing (MR={mr_dist}m, ZP={zp_dist}m)...")
        
        # Retrieve spatial SRID from baseline table
        with conn.cursor() as cur:
            try:
                cur.execute(f"SELECT Find_SRID('public', '{osm_table}', 'geometry')")
                srid = cur.fetchone()[0] or base_network.srid
            except Exception:
                srid = base_network.srid
                
        diag_prefix = f"{location_prefix}_{context.scenario_id}"
        
        # Initialize spatial diagnostic layers
        execute_query(conn, f"DROP TABLE IF EXISTS {diag_prefix}_diag_assim_buffers; CREATE TABLE {diag_prefix}_diag_assim_buffers (project_id BIGINT, geometry GEOMETRY(Geometry, {srid}));")
        execute_query(conn, f"DROP TABLE IF EXISTS {diag_prefix}_diag_shattered_segments; CREATE TABLE {diag_prefix}_diag_shattered_segments (parent_baseline_id BIGINT, project_id TEXT, highway TEXT, geometry GEOMETRY(Geometry, {srid}), overlap_pct DOUBLE PRECISION);")
        execute_query(conn, f"DROP TABLE IF EXISTS {diag_prefix}_diag_nodal_snaps; CREATE TABLE {diag_prefix}_diag_nodal_snaps (project_id TEXT, geometry GEOMETRY(Geometry, {srid}));")
        execute_query(conn, f"DROP TABLE IF EXISTS {diag_prefix}_diag_isolated_nodes; CREATE TABLE {diag_prefix}_diag_isolated_nodes (project_id TEXT, geometry GEOMETRY(Geometry, {srid}));")
        execute_query(conn, f"DROP TABLE IF EXISTS {diag_prefix}_diag_plugging_links; CREATE TABLE {diag_prefix}_diag_plugging_links (project_id TEXT, geometry GEOMETRY(Geometry, {srid}));")
        
        assimilated_segments = "temp_assimilated_segments"
        
        # Identify project archetypes (Single-Edge vs Multi-Edge)
        with conn.cursor() as cur:
            cur.execute(f"SELECT id, COUNT(*) FROM {projects_table} GROUP BY id")
            stats = cur.fetchall()
            single_edge_pids = [row[0] for row in stats if row[1] == 1]
            multi_edge_pids = [row[0] for row in stats if row[1] > 1]

        # Track A: Standard Iterative Shatter (for Multi-Edge)
        if multi_edge_pids:
            if context.observer:
                context.observer.report_diagnostic("SHATTER", "INFO", f"Applying iterative shatter to {len(multi_edge_pids)} multi-edge projects...")
            
            multi_ids_str = ",".join(map(str, multi_edge_pids))
            execute_query(conn, f"""
                DROP TABLE IF EXISTS multi_edge_projects; 
                CREATE TEMP TABLE multi_edge_projects AS 
                SELECT (ST_Dump(ST_MakeValid(geometry))).geom as geometry, id as id 
                FROM {projects_table} 
                WHERE id IN ({multi_ids_str});
                CREATE INDEX multi_edge_projects_gix ON multi_edge_projects USING GIST (geometry);
            """)
            
            assim_buffers = "temp_assimilation_buffers"
            execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'create_assimilation_buffers.sql')).format(
                result_table=assim_buffers,
                projects_table="multi_edge_projects",
                ref_snap_dist=mr_dist
            ))

            execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'resolve_assimilation_conflicts.sql')).format(
                result_table=assimilated_segments,
                baseline_table=osm_table,
                buffers_table=assim_buffers
            ))
            
            # Save multi-edge diagnostics
            execute_query(conn, f"TRUNCATE {diag_prefix}_diag_assim_buffers; INSERT INTO {diag_prefix}_diag_assim_buffers SELECT * FROM {assim_buffers};")
            execute_query(conn, f"TRUNCATE {diag_prefix}_diag_shattered_segments; INSERT INTO {diag_prefix}_diag_shattered_segments SELECT * FROM {assimilated_segments};")

            # Apply Assimilation
            execute_query(conn, f"DELETE FROM {osm_table} WHERE id IN (SELECT parent_baseline_id FROM {assimilated_segments});")
            execute_query(conn, f"""
                INSERT INTO {osm_table} (geometry, highway, is_project, project_id, parent_baseline_id, impedance) 
                SELECT geometry, 'project_assimilated', TRUE, project_id::text, parent_baseline_id, 0.5 
                FROM {assimilated_segments};
            """)
            
            # Innovation path for multi-edge: geometries that do not significantly overlap baseline
            execute_query(conn, f"""
                INSERT INTO {osm_table} (geometry, highway, is_project, project_id, impedance) 
                SELECT p.geometry, 'project_innovation', TRUE, p.id::text, 0.5 
                FROM multi_edge_projects p 
                WHERE NOT EXISTS (
                    SELECT 1 FROM {assimilated_segments} s 
                    WHERE s.project_id::bigint = p.id 
                      AND ST_Intersects(p.geometry, s.geometry)
                      AND ST_Length(ST_Intersection(p.geometry, s.geometry)) > 0.5 * ST_Length(p.geometry)
                );
            """)
        else:
            execute_query(conn, f"CREATE TEMP TABLE {assimilated_segments} (project_id TEXT, parent_baseline_id TEXT, geometry GEOMETRY);")

        # Track B: Nodalized Sutura Pattern (for Single-Edge)
        if single_edge_pids:
            if context.observer:
                context.observer.report_diagnostic("SUTURA", "INFO", f"Applying Nodalized Sutura to {len(single_edge_pids)} single-edge projects...")
            
            single_ids_str = ",".join(map(str, single_edge_pids))
            execute_query(conn, f"""
                INSERT INTO {osm_table} (geometry, highway, is_project, project_id, impedance) 
                SELECT (ST_Dump(ST_MakeValid(geometry))).geom, 'project_innovation', TRUE, id::text, 0.5 
                FROM {projects_table} WHERE id IN ({single_ids_str});
            """)
            
            # Sequential single-edge link sutures
            for pid in single_edge_pids:
                execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'link_single_edge_project.sql')).format(
                    network_table=osm_table,
                    pid=pid,
                    ref_snap_dist=mr_dist,
                    project_influence_dist=zp_dist,
                    diag_snaps_table=f"{diag_prefix}_diag_nodal_snaps"
                ))

        # 3. INHIBITION (Impedance Surface)
        if context.observer:
            context.observer.on_progress_update("Refactorización de la Topología", increment=1)

        execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'create_impedance_buffers.sql')).format(
            result_table=f'{scenery_name}_imp_buff', 
            table_name=osm_table, 
            dist_buffer=context.buffer_size, 
            high_impedance=context.imp_primary, 
            medium_impedance=context.imp_secondary, 
            low_impedance=context.imp_tertiary, 
            else_impedance=context.imp_local
        ))

        use_buffer = f'{scenery_name}_imp_buff'
        if context.disinhibit:
            if context.observer:
                context.observer.report_diagnostic("DISINHIBITION", "INFO", "Executing cycleway desinhibition buffer subtraction...")
            
            des_lines = f'{scenery_name}_desinhibitor_lines'
            execute_query(conn, f"DROP TABLE IF EXISTS public.{des_lines};")
            execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'union_desinhibit.sql')).format(
                desinhibitor_name=des_lines,
                ciclo_table=ciclo_table,
                desinhibitor_table=projects_table,
                filters=""
            ))
            
            des_buff = f'{scenery_name}_desinhibitor_buff'
            execute_query(conn, f"DROP TABLE IF EXISTS buffers.{des_buff};")
            execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'create_buffer.sql')).format(
                result_table=des_buff,
                table_name=f"public.{des_lines}",
                dist_buffer=context.buffer_size
            ))
            
            imp_diff = f'{scenery_name}_imp_diff'
            execute_query(conn, f"DROP TABLE IF EXISTS buffers.{imp_diff};")
            execute_query(conn, f"DROP TABLE IF EXISTS buffers.{scenery_name}_inhib_diff;")
            execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'buffer_difference.sql')).format(
                inhib_name=f'{scenery_name}_inhib_diff',
                buffer_inhibitor=f'{scenery_name}_imp_buff',
                buffer_desinhibitor=des_buff,
                impedance_name=imp_diff,
                buffer_impedance=f'{scenery_name}_imp_buff'
            ))
            use_buffer = imp_diff

        execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'create_inhibited_network.sql')).format(
            result_name=scenery_name, 
            network_table=osm_table, 
            inhib_buffer=use_buffer, 
            impedance_buffer=use_buffer
        ))

        # 4. MERGING (Projects already integrated in scenery_name for manual scenario)
        execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'create_full_network.sql')).format(
            result_name=internal_net_table, 
            ciclo=ciclo_table, 
            osm=scenery_name, 
            filters="", 
            bike_impedance=context.imp_bike,
            projects_union=""
        ))

        # 5. FINAL TOPOLOGICAL REPAIR
        if context.observer:
            context.observer.report_diagnostic("TOPOLOGY_FINAL", "INFO", "Building final routing topology...")
            
        execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'create_routing_topology.sql')).format(
            table=internal_net_table, 
            tolerance=0.1
        ))

        # 6. Snap Baseline Cycleways (Welding)
        _weld_cycleways(conn, internal_net_table, context.observer)

        # 7. Project Endpoint Plugging
        if context.observer:
            context.observer.report_diagnostic("NODALIZATION", "INFO", "Executing Project-specific Nodalization & Repair...")
        
        with conn.cursor() as cur:
            cur.execute(f"SELECT DISTINCT project_id FROM {internal_net_table} WHERE is_project = TRUE")
            project_ids = [row[0] for row in cur.fetchall()]

        for pid in project_ids:
            if not pid: continue
            if context.observer:
                context.observer.report_diagnostic("PROJECT_PLUG", "INFO", f"Plugging project endpoints: {pid}")
            execute_query(conn, read_sql_file(os.path.join(context.sql_base_path, 'plug_project_nodes.sql')).format(
                network_table=internal_net_table,
                ref_snap_dist=mr_dist,
                pid=pid,
                diag_nodes_table=f"{diag_prefix}_diag_isolated_nodes",
                diag_links_table=f"{diag_prefix}_diag_plugging_links"
            ))

        # 8. Final Graph Cleaning
        execute_query(conn, f"DELETE FROM {internal_net_table} WHERE ST_Length(geometry) < 0.5;")

        # Diagnostic metadata registry
        diag_tables = {
            'assim_buffers': f"{diag_prefix}_diag_assim_buffers",
            'shattered_segments': f"{diag_prefix}_diag_shattered_segments",
            'nodal_snaps': f"{diag_prefix}_diag_nodal_snaps",
            'isolated_nodes': f"{diag_prefix}_diag_isolated_nodes",
            'plugging_links': f"{diag_prefix}_diag_plugging_links"
        }

        return RefactorResult(
            scenery_table=scenery_name, 
            internal_net_table=internal_net_table,
            diagnostic_tables=diag_tables
        )


def _weld_cycleways(conn: Any, internal_net_table: str, observer: Optional[ProgressSeam]):
    """Helps snap and weld baseline cycleways to street nodes."""
    if observer:
        observer.report_diagnostic("CYCLEWAY_WELD", "INFO", "Welding isolated baseline cycleway endpoints to street network...")
    
    execute_query(conn, f"""
        DROP TABLE IF EXISTS temp_cycleway_node_degrees;
        CREATE TEMP TABLE temp_cycleway_node_degrees AS
        SELECT node_id, COUNT(*) as degree
        FROM (
            SELECT source as node_id FROM {internal_net_table} WHERE original_highway = 'cycleway'
            UNION ALL
            SELECT target as node_id FROM {internal_net_table} WHERE original_highway = 'cycleway'
        ) sub
        GROUP BY node_id;

        DROP TABLE IF EXISTS temp_isolated_cycleway_nodes;
        CREATE TEMP TABLE temp_isolated_cycleway_nodes AS
        SELECT 
            d.node_id,
            v.the_geom
        FROM temp_cycleway_node_degrees d
        JOIN {internal_net_table}_vertices_pgr v ON d.node_id = v.id
        WHERE d.degree = 1 -- Only snap dead-ends of cycleways!
          AND NOT EXISTS (
              SELECT 1 FROM {internal_net_table} e 
              WHERE (e.source = d.node_id OR e.target = d.node_id) 
                AND e.original_highway != 'cycleway'
          );

        DROP TABLE IF EXISTS temp_cycleway_plugging_map;
        CREATE TEMP TABLE temp_cycleway_plugging_map AS
        SELECT DISTINCT ON (i.node_id)
            i.node_id as isolated_node_id,
            target.id as target_node_id
        FROM temp_isolated_cycleway_nodes i
        CROSS JOIN LATERAL (
            SELECT v.id 
            FROM {internal_net_table}_vertices_pgr v
            WHERE v.id NOT IN (SELECT node_id FROM temp_isolated_cycleway_nodes)
              AND ST_DWithin(i.the_geom, v.the_geom, 30.0)
              AND EXISTS (SELECT 1 FROM {internal_net_table} e WHERE (e.source = v.id OR e.target = v.id) AND e.original_highway != 'cycleway')
            ORDER BY i.the_geom <-> v.the_geom
            LIMIT 1
        ) target;

        UPDATE {internal_net_table} SET source = m.target_node_id 
        FROM temp_cycleway_plugging_map m 
        WHERE source = m.isolated_node_id AND original_highway = 'cycleway';

        UPDATE {internal_net_table} SET target = m.target_node_id 
        FROM temp_cycleway_plugging_map m 
        WHERE target = m.isolated_node_id AND original_highway = 'cycleway';
    """)


class RefactorStrategyFactory:
    """
    Factory to resolve the correct RefactorStrategy.
    """
    @staticmethod
    def get_strategy(config: ScenarioConfig) -> RefactorStrategy:
        if config.scenario_id.startswith("rec_"):
            return RecommendationStrategy()
        elif config.projects_input:
            return SuturaRefactorStrategy()
        else:
            return TrivialIdentityStrategy()


class SpatialRefactorAdapter:
    """
    Backward-compatible wrapper mapping the legacy ScenarioEngine Task call
    to the deep RefactorStrategy seam.
    """
    def __init__(self, conn: Any, sql_base_path: str, observer: Optional[ProgressSeam] = None):
        self.conn = conn
        self.sql_base_path = sql_base_path
        self.observer = observer

    def refactor(self, config: ScenarioConfig, tables: Dict[str, str]) -> str:
        # 1. Resolve strategy dynamically using the factory
        strategy = RefactorStrategyFactory.get_strategy(config)
        
        # 2. Build parameter objects to satisfy the seam interface
        base_network = NetworkGraphRef(
            connection=self.conn,
            osm_table=tables['osm'],
            ciclo_table=tables['ciclo'],
            net_table=tables['net'],
            srid=getattr(config, 'srid', 32719)
        )
        
        layers = []
        if config.projects_input:
            layers.append(
                ProjectLayer(
                    layer_id="projects",
                    projects_table=tables['projects'],
                    ref_snap_dist=getattr(config, 'ref_snap_dist', 5.0),
                    project_influence_dist=getattr(config, 'project_influence_dist', 25.0),
                    cycleway_impedance=config.imp_bike
                )
            )
            
        context = RefactorContext(
            scenario_id=config.scenario_id,
            location=config.location,
            sql_base_path=self.sql_base_path,
            observer=self.observer,
            buffer_size=config.buffer_size,
            disinhibit=config.disinhibit,
            imp_primary=config.imp_primary,
            imp_secondary=config.imp_secondary,
            imp_tertiary=config.imp_tertiary,
            imp_local=config.imp_local,
            imp_bike=config.imp_bike
        )
        
        # 3. Execute the polymorphic refactor strategy
        result = strategy.refactor(base_network, layers, context)
        return result.scenery_table
