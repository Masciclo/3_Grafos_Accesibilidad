import os
from core.pipeline import PipelineTask, ScenarioContext
from infra.ingestion import DataIngestor, download_h3, create_abbreviation
from infra.database import execute_query, read_sql_file
from core import routing, results
from core.network_refactor import SpatialRefactorAdapter
from core.routing_visualizer import RoutingVisualizer

class IngestionTask(PipelineTask):
    @property
    def stage_id(self) -> int: return 1
    @property
    def name(self) -> str: return "Data Ingestion"

    def execute(self, context: ScenarioContext):
        # Delegate the multi-dataset ingestion to the deep DataIngestor module
        ingestor = DataIngestor(context.conn, context.db_config, context.observer)
        manifest = ingestor.ingest(context.config, context.tables)
        context.state['ingestion_manifest'] = manifest

class TopologyTask(PipelineTask):
    @property
    def stage_id(self) -> int: return 2
    @property
    def name(self) -> str: return "Topology Creation"

    def execute(self, context: ScenarioContext):
        sql_path = context.state['sql_base_path']
        execute_query(context.conn, read_sql_file(os.path.join(sql_path, 'create_routing_topology.sql')).format(table=context.tables['osm'], tolerance=0.1))
        execute_query(context.conn, read_sql_file(os.path.join(sql_path, 'calculate_components.sql')).format(topo_name=f"{context.tables['osm']}_vertices_pgr", result_table=f"{context.tables['osm']}_components", table_name=context.tables['osm']))

class RefactorTask(PipelineTask):
    @property
    def stage_id(self) -> int: return 5
    @property
    def name(self) -> str: return "Topological Refactor"

    def execute(self, context: ScenarioContext):
        # Instantiate the deep SpatialRefactorAdapter module
        adapter = SpatialRefactorAdapter(context.conn, context.state['sql_base_path'], context.observer)
        context.state['scenery_table'] = adapter.refactor(context.config, context.tables)

class RoutingTask(PipelineTask):
    @property
    def stage_id(self) -> int: return 7
    @property
    def name(self) -> str: return "Demand Routing"

    def execute(self, context: ScenarioContext):
        # Instantiate the deep RoutingOrchestrator module
        orchestrator = routing.RoutingOrchestrator(
            context.conn, context.db_config, 
            context.state['sql_base_path'], context.observer
        )
        context.state['components_table'] = orchestrator.route(context.config, context.tables)

class ResultsTask(PipelineTask):
    """
    ResultsTask: Handles Stage 8 and Data Finalization. 
    """
    @property
    def stage_id(self) -> int: return 8
    @property
    def name(self) -> str: return "Analytical Closure"

    def execute(self, context: ScenarioContext):
        config = context.config
        tables = context.tables
        location_prefix = create_abbreviation(config.location)
        scenario_prefix = f"{location_prefix}_{config.scenario_id}"
        sql_path = context.state['sql_base_path']
        
        # Instantiate the deep ResultsAggregator
        aggregator = results.ResultsAggregator(context.conn, context.observer)
        
        # Parity assertions
        results.SchemaGuard.ensure_h3_parity(context.conn, tables['h3'])
        results.SchemaGuard.ensure_network_parity(context.conn, tables['net'])
        
        # Delta Calculation
        if config.reference_scenario:
            from infra.database import check_table_existence
            results.diagnostic_handler.report("DELTA_ENGINE", "INFO", f"Calculating Delta against: {config.reference_scenario}")
            delta_table_name = f"{scenario_prefix}_delta_network"
            internal_base = f"{location_prefix}_{config.reference_scenario}_internal_net"
            final_base = f"{location_prefix}_{config.reference_scenario}_network"
            
            baseline_network = None
            if check_table_existence(context.conn, internal_base):
                baseline_network = internal_base
            elif check_table_existence(context.conn, final_base):
                baseline_network = final_base
                
            if baseline_network:
                delta_strategy = results.LineagePersistenceStrategy(sql_path, ma_distance=config.ma_distance)
                metrics = aggregator.calculate_delta(tables['net'], baseline_network, delta_table_name, delta_strategy)
                results.diagnostic_handler.report("DELTA_COMPLETE", "INFO", f"Delta layer created: {metrics.delta_table_name}")
            else:
                results.diagnostic_handler.report("DELTA_FAILED", "WARNING", f"No baseline network found for {config.reference_scenario}.")
                
        # H3 Aggregations
        from infra.database import check_table_existence
        has_components = check_table_existence(context.conn, f"{tables['net']}_components")
        queries = [
            ('osm_data_to_h3.sql', tables['osm'], 'osm'),
            ('ciclo_data_to_h3.sql', tables['ciclo'], 'ciclo')
        ]
        if has_components:
            queries.append(('components_data_to_h3.sql', f"{tables['net']}_components", 'components'))
        if config.projects_input:
            queries.append(('projects_data_to_h3.sql', tables['projects'], 'projects'))
        if config.census_input:
            queries.append(('census_data_to_h3.sql', tables['census'], 'census'))
        if config.od_input:
            queries.append(('demand_data_to_h3.sql', tables['net'], 'demand'))
            
        agg_strategy = results.DirectSQLTemplateStrategy(sql_path)
        for script, source_table, key in queries:
            params = {}
            if key == 'osm':
                params = {'osm_table': tables['osm'], 'h3_table': tables['h3']}
            elif key == 'ciclo':
                params = {'ciclo_table': tables['ciclo'], 'h3_table': tables['h3']}
            elif key == 'components':
                params = {'component_table': f"{tables['net']}_components", 'h3_table': tables['h3']}
            elif key == 'projects':
                params = {'projects_table': tables['projects'], 'h3_table': tables['h3']}
            elif key == 'census':
                params = {'census_table': tables['census'], 'h3_table': tables['h3'], 'srid': config.srid}
            elif key == 'demand':
                params = {'network_table': tables['net'], 'h3_table': tables['h3']}
                
            aggregator.aggregate_to_h3(tables['h3'], source_table, script, params, agg_strategy)
            
        # Stage 9 (Part A): Final DB Aggregation
        aggregator.finalize_qgis(scenario_prefix, tables['net'], tables['h3'], tables['ciclo'], sql_path)
        if tables.get('zones'):
            aggregator.calculate_mcp(scenario_prefix, tables['zones'], tables['h3'], sql_path)
            
        # Denominator trips check
        total_trips = aggregator.extract_total_trips(scenario_prefix)
        context.state['total_trips'] = total_trips

class GridTask(PipelineTask):
    @property
    def stage_id(self) -> int: return 3
    @property
    def name(self) -> str: return "Grid Extraction"

    def execute(self, context: ScenarioContext):
        config = context.config
        tables = context.tables
        
        # Extract DB credentials from context
        db_cfg = context.db_config
        user, password, host, port, db = db_cfg.get('user'), db_cfg.get('password'), db_cfg.get('host'), db_cfg.get('port'), db_cfg.get('name')
        
        # Robust parsing for env and config
        try:
            raw_h3 = os.getenv('H3_LEVEL', '9')
            h3_res = int(raw_h3) if str(raw_h3).lower() != 'none' else 9
        except (ValueError, TypeError):
            h3_res = 9
            
        try:
            srid_val = int(config.srid) if str(config.srid).lower() != 'none' else 4326
        except (ValueError, TypeError):
            srid_val = 4326

        download_h3(
            tables['zones'], tables['h3'], srid_val, h3_res, 
            user, password, host, port, db,
            callback=lambda *args, **kwargs: context.observer.on_progress_update(*args, **kwargs)
        )
        execute_query(context.conn, read_sql_file(os.path.join(context.state['sql_base_path'], 'prune_h3_to_mcp.sql')).format(zones_table=tables['zones'], h3_table=tables['h3']))

class MappingTask(PipelineTask):
    @property
    def stage_id(self) -> int: return 9
    @property
    def name(self) -> str: return "Academic Mapping"

    def execute(self, context: ScenarioContext):
        if not context.config.mapping:
            return
            
        visualizer = RoutingVisualizer(context)
        visualizer.execute()
