import unittest
from core.ontology import (
    SpatialAnchorType,
    TargetAttractorType,
    GrowthMorphology,
    BudgetConstraintMode,
    ProjectTaxonomySpec,
    UrbanOntologyInterpretation
)

class TestUrbanOntology(unittest.TestCase):

    def test_taxonomy_enums(self):
        self.assertEqual(SpatialAnchorType.COMPONENT_TIP.value, "component_tip")
        self.assertEqual(TargetAttractorType.DEMAND_CENTROID.value, "demand_centroid")
        self.assertEqual(GrowthMorphology.SINGLE_PATH_CORRIDOR.value, "single_path_corridor")
        self.assertEqual(BudgetConstraintMode.FIXED_PER_PROJECT.value, "fixed_per_project")

    def test_smart_defaults_for_underspecified_prompt(self):
        raw_prompt = "give me 10 random 1km high value extensions of the network"
        parsed_dict = {
            "total_projects": 10,
            "default_budget_per_project_m": 1000.0,
            "global_seed_strategy": SpatialAnchorType.DEMAND_HOTSPOT.value
        }
        
        ontology = UrbanOntologyInterpretation.apply_smart_defaults("santiago", raw_prompt, parsed_dict)
        
        self.assertEqual(ontology.total_projects, 10)
        self.assertEqual(ontology.default_budget_per_project_m, 1000.0)
        self.assertEqual(len(ontology.projects), 10)
        self.assertEqual(ontology.projects[0].anchor_type, SpatialAnchorType.DEMAND_HOTSPOT)
        self.assertEqual(ontology.projects[0].budget_m, 1000.0)
        print("✅ test_smart_defaults_for_underspecified_prompt PASSED!")

    def test_ingestion_ontology_schemas(self):
        from core.ontology import (
            IngestibilityStatus,
            SpatialSanityType,
            SchemaAlignmentType,
            SanitationActionType,
            FileDiagnosticReport,
            SanitationRecipe
        )
        
        report = FileDiagnosticReport(
            filename="Zonas_EOD.shp",
            filepath="data/santiago/raw/Zonas_EOD.shp",
            status=IngestibilityStatus.INGESTABLE_REPAIRABLE,
            spatial_sanity=SpatialSanityType.CRS_REPROJECT_NEEDED,
            schema_alignment=SchemaAlignmentType.ALIAS_MAPPABLE,
            detected_crs="EPSG:4326",
            detected_columns=["ID_ZONA", "NOMBRE"],
            proposed_actions=[SanitationActionType.REPROJECT_CRS, SanitationActionType.REMAP_COLUMNS],
            issues_summary=["Non-standard column ID_ZONA", "CRS is EPSG:4326"]
        )
        
        recipe = SanitationRecipe(
            city_key="santiago",
            target_srid=32719,
            verdict=IngestibilityStatus.INGESTABLE_REPAIRABLE,
            file_reports=[report],
            column_mapping={"ID_ZONA": "zone_id"},
            reproject_files=["Zonas_EOD.shp"]
        )
        
        self.assertEqual(recipe.verdict, IngestibilityStatus.INGESTABLE_REPAIRABLE)
        self.assertEqual(recipe.column_mapping["ID_ZONA"], "zone_id")
        self.assertEqual(recipe.reproject_files[0], "Zonas_EOD.shp")
        print("✅ test_ingestion_ontology_schemas PASSED!")

    def test_cumulative_greedy_growth(self):
        from core.recommendation import RecommendationEngine
        import inspect
        sig = inspect.signature(RecommendationEngine._solve_greedy_growth)
        self.assertIn("accumulated_upgrades", sig.parameters)
        param = sig.parameters["accumulated_upgrades"]
        self.assertEqual(param.default, None)
        print("✅ test_cumulative_greedy_growth_signature PASSED!")

if __name__ == "__main__":
    unittest.main()

