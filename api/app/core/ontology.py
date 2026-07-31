"""
+Ciclo Unified Urban Recommendation Taxonomy & Ontology Subsystem (Ontology v1)
Provides formal type definitions, Enums, Pydantic schemas, and smart fallback rules
for interpreting natural language recommendation prompts into spatial graph execution parameters.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class SpatialAnchorType(str, Enum):
    """Taxonomy 1: Spatial Anchor (Where the project seed originates)"""
    COMPONENT_TIP = "component_tip"  # Endpoint of largest cycleway component
    DEMAND_HOTSPOT = "demand_hotspot"  # Origin/destination H3 trip cluster
    NETWORK_GAP = "network_gap"  # Unconnected street between existing cycleways
    HIGH_VOLUME_CORRIDOR = "high_volume_corridor"  # High baseline flow avenue


class TargetAttractorType(str, Enum):
    """Taxonomy 2: Target Attractor (Directional gravity vector v_target)"""
    URBAN_CENTER = "urban_center"  # CBD / Central square
    POI_CLUSTER = "poi_cluster"  # School/Hospital/Commercial POIs
    DEMAND_CENTROID = "demand_centroid"  # Gravity centroid of active trips
    DIRECTIONAL_VECTOR = "directional_vector"  # Cardinal orientation (N/S/E/W)


class GrowthMorphology(str, Enum):
    """Taxonomy 3: Growth Topology (Shape of the upgraded corridor)"""
    SINGLE_PATH_CORRIDOR = "single_path_corridor"  # Continuous non-dendritic 1D trunk
    NETWORK_STITCHING = "network_stitching"  # Topological bridge between sub-networks
    FEEDER_BRANCH = "feeder_branch"  # Radial feeder extending from main artery


class BudgetConstraintMode(str, Enum):
    """Taxonomy 4: Resource Allocation & Budget Constraint"""
    FIXED_PER_PROJECT = "fixed_per_project"  # Fixed physical length per project (e.g. 1000m)
    GLOBAL_CITY_BUDGET = "global_city_budget"  # Shared citywide meter budget
    HIGH_VALUE_THRESHOLD = "high_value_threshold"  # Min CER capture ratio requirement


class ProjectTaxonomySpec(BaseModel):
    """Formal Taxon for an Individual Recommendation Project"""
    project_id: str = Field(description="Unique identifier e.g. rec_1")
    name: str = Field(description="Human-readable project corridor title")
    anchor_type: SpatialAnchorType = Field(default=SpatialAnchorType.COMPONENT_TIP)
    attractor_type: TargetAttractorType = Field(default=TargetAttractorType.DEMAND_CENTROID)
    morphology: GrowthMorphology = Field(default=GrowthMorphology.SINGLE_PATH_CORRIDOR)
    budget_mode: BudgetConstraintMode = Field(default=BudgetConstraintMode.FIXED_PER_PROJECT)
    budget_m: float = Field(default=1000.0, description="Project budget/length limit in meters")
    target_attractor_label: Optional[str] = Field(default=None, description="Specific destination landmark or direction")


class UrbanOntologyInterpretation(BaseModel):
    """Complete Taxonomical Interpretation of a User Recommendation Prompt"""
    city_key: str = Field(description="Target city key e.g. santiago, valdivia")
    raw_prompt: str = Field(description="Original user natural language request")
    interpreted_intent_summary: str = Field(description="Concise summary of the taxonomical interpretation")
    total_projects: int = Field(default=10, description="Number of projects requested")
    default_budget_per_project_m: float = Field(default=1000.0, description="Default budget per project in meters")
    global_seed_strategy: SpatialAnchorType = Field(default=SpatialAnchorType.COMPONENT_TIP)
    projects: List[ProjectTaxonomySpec] = Field(default_factory=list)

    @classmethod
    def apply_smart_defaults(cls, city_key: str, raw_prompt: str, parsed_dict: dict) -> "UrbanOntologyInterpretation":
        """Applies smart fallback defaults to under-specified natural language prompts."""
        total = parsed_dict.get("total_projects", 10)
        budget = parsed_dict.get("default_budget_per_project_m", 1000.0)
        raw_anchor = parsed_dict.get("global_seed_strategy", SpatialAnchorType.COMPONENT_TIP)
        if isinstance(raw_anchor, str):
            try:
                anchor = SpatialAnchorType(raw_anchor)
            except ValueError:
                anchor = SpatialAnchorType.COMPONENT_TIP
        else:
            anchor = raw_anchor

        projects = []
        raw_projects = parsed_dict.get("projects", [])
        
        for i in range(total):
            if i < len(raw_projects):
                p_data = raw_projects[i]
                p_spec = ProjectTaxonomySpec(
                    project_id=p_data.get("project_id", f"rec_{i+1}"),
                    name=p_data.get("name", f"Recommended Corridor {i+1}"),
                    anchor_type=p_data.get("anchor_type", anchor),
                    attractor_type=p_data.get("attractor_type", TargetAttractorType.DEMAND_CENTROID),
                    morphology=p_data.get("morphology", GrowthMorphology.SINGLE_PATH_CORRIDOR),
                    budget_mode=p_data.get("budget_mode", BudgetConstraintMode.FIXED_PER_PROJECT),
                    budget_m=float(p_data.get("budget_m", budget)),
                    target_attractor_label=p_data.get("target_attractor_label")
                )
            else:
                p_spec = ProjectTaxonomySpec(
                    project_id=f"rec_{i+1}",
                    name=f"Recommended Corridor {i+1}",
                    anchor_type=anchor,
                    attractor_type=TargetAttractorType.DEMAND_CENTROID,
                    morphology=GrowthMorphology.SINGLE_PATH_CORRIDOR,
                    budget_mode=BudgetConstraintMode.FIXED_PER_PROJECT,
                    budget_m=budget
                )
            projects.append(p_spec)


        return cls(
            city_key=city_key,
            raw_prompt=raw_prompt,
            interpreted_intent_summary=parsed_dict.get(
                "interpreted_intent_summary",
                f"Generated {total} projects ({budget}m each) using {anchor} spatial anchoring."
            ),
            total_projects=total,
            default_budget_per_project_m=budget,
            global_seed_strategy=anchor,
            projects=projects
        )


# =====================================================================
# +Ciclo Ingestion Diagnostics & Automated Data Sanitation (IngestionOntology v1)
# =====================================================================

class IngestibilityStatus(str, Enum):
    """Ingestibility Verdict for Raw City Datasets"""
    INGESTABLE_READY = "INGESTABLE_READY"  # Schema & CRS 100% compliant. Zero repair needed.
    INGESTABLE_REPAIRABLE = "INGESTABLE_REPAIRABLE"  # Repairable via Sanitation Recipe (columns, CRS, BBOX).
    NON_INGESTABLE_UNRELATED = "NON_INGESTABLE_UNRELATED"  # Corrupted, empty, or non-spatial document.


class SpatialSanityType(str, Enum):
    """Spatial Layer Geometry & Projection Status"""
    CRS_MATCH = "CRS_MATCH"  # Native CRS matches target city SRID.
    CRS_REPROJECT_NEEDED = "CRS_REPROJECT_NEEDED"  # Valid spatial layer requiring CRS reprojection.
    GEOM_CORRUPTED = "GEOM_CORRUPTED"  # Invalid topology / null geometry.
    NOT_SPATIAL = "NOT_SPATIAL"  # Non-spatial table (OD matrix, survey CSV).


class SchemaAlignmentType(str, Enum):
    """Schema & Column Name Alignment Status"""
    CANONICAL_KEYS_PRESENT = "CANONICAL_KEYS_PRESENT"  # Standard zone_id, origin, destination present.
    ALIAS_MAPPABLE = "ALIAS_MAPPABLE"  # Aliases detected (e.g. ID_ZONA -> zone_id, n_per -> pop_total).
    MISSING_CRITICAL_KEYS = "MISSING_CRITICAL_KEYS"  # Required spatial or matrix index missing.


class SanitationActionType(str, Enum):
    """Sanitation Recipe Action Types"""
    REPROJECT_CRS = "REPROJECT_CRS"  # Reproject GeoDataFrame to target SRID
    REMAP_COLUMNS = "REMAP_COLUMNS"  # Rename column aliases to canonical keys
    MERGE_COMMUNES = "MERGE_COMMUNES"  # Merge multi-commune shapefile parts into unified layer
    ARCHIVE_AUXILIARY = "ARCHIVE_AUXILIARY"  # Move non-primary shapefiles to unused/ folder
    CENSUS_BBOX_CLIP = "CENSUS_BBOX_CLIP"  # Clip nationwide/regional census to city BBOX + 15km
    FALLBACK_OSM_RESIDENTIAL = "FALLBACK_OSM_RESIDENTIAL"  # Fall back to OSM residential building footprints


class FileDiagnosticReport(BaseModel):
    """Diagnostic Audit Report for an Individual File"""
    filename: str = Field(description="Raw filename")
    filepath: str = Field(description="Absolute or relative file path")
    status: IngestibilityStatus = Field(default=IngestibilityStatus.INGESTABLE_READY)
    spatial_sanity: SpatialSanityType = Field(default=SpatialSanityType.NOT_SPATIAL)
    schema_alignment: SchemaAlignmentType = Field(default=SchemaAlignmentType.CANONICAL_KEYS_PRESENT)
    detected_crs: Optional[str] = Field(default=None)
    detected_columns: List[str] = Field(default_factory=list)
    proposed_actions: List[SanitationActionType] = Field(default_factory=list)
    issues_summary: List[str] = Field(default_factory=list)


class SanitationRecipe(BaseModel):
    """Executable Sanitation Recipe for a City's Raw Directory"""
    city_key: str = Field(description="Target city key e.g. santiago, valdivia")
    target_srid: int = Field(default=4326)
    verdict: IngestibilityStatus = Field(default=IngestibilityStatus.INGESTABLE_READY)
    file_reports: List[FileDiagnosticReport] = Field(default_factory=list)
    archive_files: List[str] = Field(default_factory=list, description="Files to move to unused/ folder")
    column_mapping: dict = Field(default_factory=dict, description="Detected column rename dictionary")
    reproject_files: List[str] = Field(default_factory=list, description="Files needing CRS reprojection")
    merge_communes: dict = Field(default_factory=dict, description="Shapefiles to merge")
    census_bbox_clip: Optional[str] = Field(default=None, description="Census file path needing BBOX clipping")
    use_osm_residential_fallback: bool = Field(default=False, description="Whether to fall back to OSM buildings")

