# 🚴‍♂️ +Ciclo Engine: REVIEW. REPAIR. RECOMMEND.

> **Active Mobility Demand Assignment, Topological Refactoring & Generative Network Design Engine**

[![Apache 2.0 License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Docker Compose](https://img.shields.io/badge/Docker_Compose-Active-brightgreen)](docker-compose.yml)
[![PostGIS](https://img.shields.io/badge/PostGIS-3.3+-blue)](https://postgis.net/)
[![pgRouting](https://img.shields.io/badge/pgRouting-3.5+-orange)](https://pgrouting.org/)
[![H3 Grid](https://img.shields.io/badge/H3_Discrete_Grid-Res_8%2F9-hexagon)](https://h3geo.org/)

---
<img width="1340" height="932" alt="image" src="https://github.com/user-attachments/assets/ae2e3c28-5899-45f1-b1fb-cbf733237b47" />

---

## 🔍 1. REVIEW: Baseline Evaluation & Diagnostics

Evaluate existing street network conditions, compute OD-weighted betweenness centrality, and isolate major traffic barriers before investing capital.

### ⚡ Quickstart & Installation Guide

#### Prerequisites
* [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with Docker Compose)
* 8 GB+ RAM (16 GB recommended for metropolitan runs)

#### Step 1: Clone Repository
```bash
git clone https://github.com/Masciclo/grafos-accesibilidad.git
cd grafos-accesibilidad
```

#### Step 2: Launch Database & App Containers
```bash
docker compose up -d --build
```

#### Step 3: Run Baseline Review for Any City
```bash
docker compose run --rm ciclo-py python main.py \
  --location valdivia \
  --scenario_id baseline \
  --yes
```
*Outputs interactive Plotly HTML maps in `data/valdivia/out/maps/`.*

---

## 🛠️ 2. REPAIR: Topological Refactoring & Project Intervention

Inject hand-drawn or proposed GeoJSON/Shapefile project lines into the street network graph. The refactoring engine automatically:
* **Amputates** overlapping baseline street edges to prevent artificial capacity duplication ($80\%$ buffer overlap).
* **Sutures** project endpoints within a spatial tolerance window (`--manual_digitization_error`).
* **Tracks Parent Lineage** to map edge IDs between topologically distinct networks.

### 🧪 Ingesting & Evaluating Custom Projects

```bash
docker compose run --rm ciclo-py python main.py \
  --location valdivia \
  --projects_input data/valdivia/raw/projects/project_1.geojson \
  --reference_scenario baseline \
  --scenario_id proj_vs_baseline \
  --manual_digitization_error 15 \
  --yes
```
*Generates differential flow maps ($\Delta f$) and $\Delta\sigma$ quantile heatmaps showing traffic diversion away from high-stress avenues.*

---

## 🤖 3. RECOMMEND: Generative Network Design Engine

Automatically generate high-utility cycleway expansion corridors under budget constraints. Powered by **Group Centrality Maximization** and **Batch Uniform Sampling (BUS)**, the engine:
* Ranks disconnected cycleway clusters by physical size.
* Executes a budget-constrained greedy Dijkstra growth loop ($1,500\text{ m}$ per corridor).
* Applies zero-cost bridging links to stitch isolated subnetworks back into the primary urban component.

### 💡 Launching AI-Assisted Recommendation Scenarios

```bash
docker compose run --rm ciclo-py python main.py \
  --location santiago \
  --reference_scenario baseline \
  --recommendation "conectar los 5 clusters por tamano de cluster" \
  --rec_budget_m 1500 \
  --rec_num_projects 10 \
  --rec_sample_size 1000 \
  --yes
```

---

## 🏗️ 4. System Architecture & Methodology

```
┌─────────────────────────┐    ┌─────────────────────────┐    ┌─────────────────────────┐
│     OSM Road Network    │    │   INE Census Parquet    │    │  OD Travel Demand MDB   │
└────────────┬────────────┘    └────────────┬────────────┘    └────────────┬────────────┘
             │                              │                              │
             └──────────────────────┬───────┴──────────────────────────────┘
                                    ▼
                     ┌─────────────────────────────┐
                     │ H3 Disaggregation (Res 8/9) │
                     └──────────────┬──────────────┘
                                    ▼
                     ┌─────────────────────────────┐
                     │   PostGIS + pgRouting A*    │
                     └──────────────┬──────────────┘
                                    ▼
                     ┌─────────────────────────────┐
                     │ Interactive Maps & Typst    │
                     └──────────────┬──────────────┘
```

### 📊 H3 Hexagonal Area-Proportional Interpolation
Coarse administrative OD zones are disaggregated onto an **H3 hexagonal grid** using population-weighted area interpolation:

$$P_H = \sum_B \left( P_B \times \frac{\text{Area}(B \cap H)}{\text{Area}(B)} \right)$$

$$T(o, d) = T_{\text{macro}}(Z_o, Z_d) \times \frac{P_o}{P_{Z_o}} \times \frac{P_d}{P_{Z_d}}$$

### ⚡ Big-O Computational Acceleration
To solve betweenness centrality across large metropolitan graphs without memory overflow:

| Routing Algorithm | Computational Complexity | Santiago Runtime ($623\text{k}$ edges) | Use Case |
| :--- | :---: | :---: | :--- |
| **Exact All-Pairs Betweenness** | $\mathcal{O}(\|V\|^2 \log \|V\|)$ | $\sim 17\text{ hours } 26\text{ min}$ | Full offline benchmark |
| **Batch Uniform Sampling (BUS)** | $\mathcal{O}(q \cdot \|V\| \log \|V\|)$ | **$\sim 1 - 3\text{ minutes}$** | Interactive sketching & recommendations |

---

## 🎛️ 5. CLI Flags Reference Guide

| Flag | Category | Default | Description |
| :--- | :---: | :---: | :--- |
| `--location` | Target | *(Required)* | Target city name or spatial bounding box. |
| `--scenario_id` | Target | `"v1"` | Unique identifier string for scenario tables. |
| `--projects_input` | Ingestion | `None` | Path to custom GeoJSON/Shapefile project lines. |
| `--reference_scenario` | Comparison | `None` | Reference scenario ID for differential $\Delta\sigma$ maps. |
| `--recommendation` | Generative | `None` | Natural language prompt for AI-assisted cycleway growth. |
| `--rec_budget_m` | Generative | `1500.0` | Allocated budget per project corridor in meters. |
| `--rec_num_projects` | Generative | `10` | Number of sequential project corridors to generate. |
| `--manual_digitization_error` | Sampling | `25.0` | Spatial tolerance buffer (meters) for project snapping. |
| `--rec_sample_size` | Sampling | `1000` | Sample size of active OD pairs for Dijkstra optimization. |
| `--yes` | Execution | `False` | Autonomous mode (bypasses CLI prompts). |

---

## 🎓 6. Academic Citation & License

If you use **+Ciclo** in your academic research, thesis, or urban planning work, please cite:

```bibtex
@mastersthesis{vergara2026masciclo,
  author       = {Vergara, Jaime},
  title        = {Optimizing Infrastructure Investment using OD-Weighted Centrality},
  school       = {Delft University of Technology (TU Delft)},
  year         = {2026},
  note         = {GEO 5010 Research Assignment, Supervised by Prof. Giorgio Agugiaro}
}
```

### 📄 License
Copyright © 2026 **+Ciclo Project** (Jaime Vergara & Gabriel Oyarzún).  
Licensed under the [Apache License, Version 2.0](LICENSE).
