# Phase 37: Cumulative Sequential Recommendation Growth (`Cumulative Greedy Growth`) Specification

## Problem Statement

When the urban recommendation engine (`+Ciclo Ontology v1`) generates $N$ recommended bikelane corridors for a city (e.g. `rec_1` through `rec_10`), each project is currently evaluated independently against the static baseline reference network (`santchil_current_internal_net`).

As a result, project `rec_7` cannot recognize that projects `rec_1` through `rec_6` have already been planned and designated as cycleways. It treats those corridors as unimproved streets and cannot topologically "latch" onto or extend from their endpoints during the greedy search optimization loop. This limits the network stitching synergy during the recommendation process.

---

## Solution

Implement **Cumulative Sequential Recommendation Growth** (`Cumulative Greedy Growth`) in `InteractiveGrillAgent`:

1. **Cumulative Active Bikelanes**: During project iteration $k$, all street edges selected in previous project iterations (`rec_1` through `rec_{k-1}`) are passed to `_solve_greedy_growth()` as `accumulated_upgrades`.
2. **Dijkstra Traversal Cost Reduction**: In candidate evaluation (`pgr_dijkstra`), edges in `accumulated_upgrades` receive the reduced cycleway cost factor (`length * 0.5` / `imp_bike = 0.8`), allowing project $k$ to route through previously built corridors at zero/reduced cost.
3. **Topological Latch Points**: Endpoints of `accumulated_upgrades` are registered as valid active seed nodes when `network_stitching` growth morphology is active, allowing project $k$ to physically attach to and extend from any previously planned project.
4. **Disjoint Edge Protection**: Edges already present in `accumulated_upgrades` cannot be re-selected as new project street upgrades (ensuring 0% project overlap).

---

## User Stories

1. As an urban transportation planner, I want project `rec_2` to treat project `rec_1` as an active, low-impedance cycleway during its optimization loop, so that `rec_2` can extend or stitch into `rec_1` seamlessly.
2. As a network analyst, I want project `rec_7` to recognize all previously planned corridors (`rec_1` to `rec_6`) as valid bikelanes, so that the 10-project recommendation package forms a contiguous, highly connected network.
3. As a GIS researcher, I want the recommendation engine to maintain 0% edge overlap between project corridors, so that each recommended project represents distinct, new physical infrastructure.
4. As a decision maker, I want to see cumulative network growth metrics where subsequent projects build upon and amplify the accessibility impact of earlier projects.

---

## Implementation Decisions

### Decision 1: `accumulated_upgrades` Tracking in `generate_projects`
Modify `InteractiveGrillAgent.generate_projects()` in `recommendation.py` to maintain a set of accumulated edge IDs (`accumulated_upgrades: set[int]`) across the sequential project loop (`idx = 0..N-1`).

### Decision 2: Integration of `accumulated_upgrades` in `_solve_greedy_growth`
Update `_solve_greedy_growth()` signature to accept `accumulated_upgrades: set[int] = None`.
- In `pgr_dijkstra` queries, cost calculation evaluates:
  $$\text{cost}(e) = \begin{cases} \text{length} \times 0.5 & \text{if } e \in E_{active} \cup E_{accumulated} \\ \text{cost}(e) & \text{otherwise} \end{cases}$$
- Candidate selection filter excludes already built edges: `WHERE id NOT IN ({active_and_accumulated_ids_str})`.

### Decision 3: Latch Point Endpoint Registration
When `accumulated_upgrades` exists, extract the source and target node IDs of all accumulated edges and add them to `active_nodes` if `network_stitching` morphology is active. This allows the search frontier to expand directly from any node of previously planned projects.

---

## Testing Decisions

### Good Test Principles
- Test external behavior: verify that candidate evaluation correctly assigns reduced cost to previously built project edges and extends from their endpoints.
- Avoid testing internal implementation details or specific SQL query strings.

### Modules to Test
- `grafos-accesibilidad/api/app/core/recommendation.py`
- `grafos-accesibilidad/api/app/test_ontology.py`

### Prior Art
- `test_ingestion_ontology_schemas` and `test_smart_defaults_for_underspecified_prompt` in `test_ontology.py`.

---

## Out of Scope

- Re-running PostGIS flow assignment after every individual project (full flow assignment remains consolidated at Stage 7 to maintain execution speed).
- Modifying baseline reference scenario tables on disk (reference scenarios remain immutable).

---

## Further Notes

- Technical Sheet #89 (`[#TS89]`) will be appended to `docs/technical-sheet.md` upon completion.
- Full backward compatibility with single-project recommendations (`num_projects = 1`) is preserved.
