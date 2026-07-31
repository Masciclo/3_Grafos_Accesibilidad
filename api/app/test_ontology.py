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

if __name__ == "__main__":
    unittest.main()
