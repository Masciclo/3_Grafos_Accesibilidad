---
name: ingestion-hygiene
description: Automatically diagnoses and resolves raw file directory ambiguities, unrecognized column schemas, and fragmented commune shapefiles prior to ingestion. Trigger this skill whenever a simulation run triggers DATA_MISSING, HYGIENIC_VIOLATION, or schema errors, or when a user requests to prepare or check raw files for a city.
---

# Ingestion Hygiene: Automated Raw Data Sanitation & Alignment (IngestionOntology v1) 🏁🧹

This skill guides the agent in diagnosing and repairing raw spatial, census, and survey data files in the encapsulated `data/[city]/raw` directories before executing the main accessibility engine. Powered by **`IngestionOntology v1`**, `PreflightDiagnosticAuditor`, and `SanitationRecipeExecutor`, it prevents failures caused by multiple shapefiles, missing column aliases, nationwide census datasets, or commune-level subdivisions.

---

## 1. Trigger Criteria

Activate this skill immediately if:
*   A pipeline run fails in **Stage 1 (Ingestion)** with `ValueError: Ambiguous File Selection`.
*   The data parser crashes with `DataProvider Error: "Could not identify Zone ID in Index(...)"`.
*   A `HYGIENIC_VIOLATION` is triggered because columns mapping origin/destination zones cannot be resolved.
*   A nationwide spatial census dataset (e.g. `census_2024_pais.parquet`) is present and needs spatial BBOX clipping.
*   The user explicitly requests to "check", "verify", or "prepare" raw files for a new city.

---

## 2. Ingestion Sanitation Workflow (`IngestionOntology v1`)

When activated, follow these steps to perform pre-flight auditing and apply an executable **Sanitation Recipe**:

### Step 1: Pre-flight Diagnostic Audit
Run `PreflightDiagnosticAuditor.audit_city_raw_directory()` to inspect the raw directories of the target city:
1.  List all files under `data/[city]/raw/[city]_zones/`, `data/[city]/raw/[city]_demand/`, and `data/[city]/raw/[city]_census.parquet`.
2.  Classify each dataset under `IngestibilityStatus` (`INGESTABLE_READY`, `INGESTABLE_REPAIRABLE`, `NON_INGESTABLE_UNRELATED`).
3.  Check CRS projections against the city target SRID (e.g. `EPSG:32719`).
4.  Inspect column names for non-standard aliases (`ID_ZONA` $\rightarrow$ `zone_id`, `origen` $\rightarrow$ `origin`, `n_per` $\rightarrow$ `pop_total`).
5.  **Spatial Scope & Census Check:** If a nationwide census dataset is present (>50,000 rows), flag for spatial BBOX clipping ($+ 15\text{km}$ buffer). If census is missing, flag for OSM residential building footprint population fallback.

### Step 2: Render Diagnostic Panel & Compile Sanitation Recipe
Display the **Pre-flight Data Sanitation Report** Rich terminal panel to the user showing file status, proposed actions, and issues.

### Step 3: Execute Sanitation Recipe
Run `SanitationRecipeExecutor.execute_recipe()` to apply approved transformations:
1.  Move auxiliary shapefiles (e.g. `Manzanas`, `Macrozonas`) to `unused/`.
2.  Reproject GeoDataFrames to the city target SRID.
3.  Rename column aliases to canonical internal keys.
4.  Clip nationwide census datasets to city BBOX $+ 15\text{km}$ buffer and save to `data/[city]/proc/census.parquet`.

### Step 4: Verification
Run `python -m unittest test_ontology.py` and `test_ingestion_satisfy.py` to confirm clean ingestion.

