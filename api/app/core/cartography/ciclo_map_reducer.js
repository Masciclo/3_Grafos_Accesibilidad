/**
 * ciclo_map_reducer.js: Pure Frontend State Reducer & Cartographic Bijective Engine.
 *
 * Implements a pure deterministic state reducer (state, action) => newState,
 * unidirectional store container (createCicloMapStore), and pure selectors
 * mapping legacy Plotly academic styling directly into MapLibre GL JS Style Expressions.
 *
 * Designed for 0.01s headless unit testing in Node.js and client-side execution
 * inside standalone GPU-accelerated MapLibre viewers.
 */

// 1. Bijective Theme Tokens Conforming to academic_maps.py
const initialThemeTokens = {
  name: "academic-plotly-bijection",

  // Context Polygons & Basemap
  basemapBackground: "#F8F9FA",
  contextWaterFill: "#CBE2EE",
  contextWaterOpacity: 0.85,
  contextForestFill: "#E8F0E8",
  contextForestOpacity: 0.80,
  contextBuildingFill: "#F0EFEA",
  contextBuildingOpacity: 0.90,
  contextUrbanLimitLine: "#E0E0E0",
  contextUrbanLimitWidth: 1.0,

  // Street Network Hierarchy (flow == 0)
  roadHierarchy: {
    motorway: "#666666",
    trunk: "#888888",
    primary: "#888888",
    secondary: "#A0A0A0",
    tertiary: "#A0A0A0",
    residential: "#C8C8C8",
    living_street: "#C8C8C8",
    unclassified: "#C8C8C8",
    default: "#D0D0D0"
  },

  // Existing Cycleways & Projects Override
  cyclewayColor: "#27ae60",
  existingCyclewayBg: "#b0d5b4",
  projectColor: "#e67e22",

  // ColorBrewer YlOrRd 5-Class Flow Palette
  flowPalette: {
    q1: "#fed976",
    q2: "#feb24c",
    q3: "#fd8d3c",
    q4: "#f03b20",
    q5: "#bd0026"
  },

  // Network Impedance Typology Palette (academic_maps.py)
  impedancePalette: {
    primary: "#e91e63",
    secondary: "#ff9800",
    tertiary: "#9c27b0",
    residential: "#2196f3",
    cycleway: "#27ae60",
    project_new: "#e67e22",
    default: "#9e9e9e"
  },

  // 9-Class Bipolar RdBu Delta Flow Palette
  deltaPalette: {
    severe_neg: "#b2182b",
    mod_neg: "#d6604d",
    mild_neg: "#f4a582",
    min_neg: "#fddbc7",
    neutral: "rgba(0,0,0,0)",
    min_pos: "#d1e5f0",
    mild_pos: "#92c5de",
    mod_pos: "#4393c3",
    severe_pos: "#2166ac"
  },

  // Sequential Green 5-Class Ramp for Bikelanes & Project Performance
  bikelanePalette: ["#c8e6c9", "#81c784", "#4caf50", "#2e7d32", "#1b5e20"],
  performancePalette: ["#c8e6c9", "#81c784", "#4caf50", "#2e7d32", "#1b5e20"],
  existingCyclewayPerformance: "#4fa8e3",

  // Distinct Trip Purpose Density Palettes
  purposePalettes: {
    work: ["#e0f7fa", "#80deea", "#26c6da", "#00acc1", "#006064"],
    study: ["#fffde7", "#fff59d", "#ffee58", "#fdd835", "#f57f17"],
    shopping: ["#fce4ec", "#f48fb1", "#ec407a", "#d81b60", "#880e4f"],
    recreational: ["#e8f5e9", "#a5d6a7", "#66bb6a", "#43a047", "#1b5e20"],
    personal: ["#e0f2f1", "#80cbc4", "#26a69a", "#00897b", "#004d40"],
    returning_home: ["#ede7f6", "#b39ddb", "#7e57c2", "#5e35b1", "#311b92"],
    default: ["#fff3e0", "#ffcc80", "#ffa726", "#fb8c00", "#e65100"]
  }
};

// 2. Initial Exploration State Tree
const initialCicloMapState = {
  viewMode: "flow", // "flow" | "impedance" | "delta"
  minFlowFilter: 0,
  cyclewaysOnly: false,
  projectsOnly: false,
  selectedEdgeId: null,
  hoveredEdgeId: null,
  activeThresholdQuantiles: {
    q1: 1,
    q2: 10,
    q3: 50,
    q4: 200,
    q5: 1000
  },
  theme: initialThemeTokens
};

/**
 * Pure State Reducer: (state, action) => newState
 * Guarantees referential immutability and deterministic state transitions.
 */
function cicloMapReducer(state = initialCicloMapState, action) {
  if (!action || !action.type) return state;

  switch (action.type) {
    case "SET_VIEW_MODE": {
      const mode = action.payload?.viewMode;
      if (!mode || state.viewMode === mode) return state;
      return { ...state, viewMode: mode };
    }

    case "SET_MIN_FLOW_FILTER": {
      const minFlow = Math.max(0, Number(action.payload?.minFlow) || 0);
      if (state.minFlowFilter === minFlow) return state;
      return { ...state, minFlowFilter: minFlow };
    }

    case "TOGGLE_CYCLEWAYS_ONLY": {
      return {
        ...state,
        cyclewaysOnly: !state.cyclewaysOnly,
        // Turn off projectsOnly if cyclewaysOnly becomes true
        projectsOnly: state.cyclewaysOnly ? state.projectsOnly : false
      };
    }

    case "TOGGLE_PROJECTS_ONLY": {
      return {
        ...state,
        projectsOnly: !state.projectsOnly,
        cyclewaysOnly: state.projectsOnly ? state.cyclewaysOnly : false
      };
    }

    case "SELECT_EDGE": {
      const edgeId = action.payload?.edgeId ?? null;
      if (state.selectedEdgeId === edgeId) return state;
      return { ...state, selectedEdgeId: edgeId };
    }

    case "HOVER_EDGE": {
      const edgeId = action.payload?.edgeId ?? null;
      if (state.hoveredEdgeId === edgeId) return state;
      return { ...state, hoveredEdgeId: edgeId };
    }

    case "SET_QUANTILES": {
      const q = action.payload?.quantiles;
      if (!q) return state;
      return {
        ...state,
        activeThresholdQuantiles: {
          ...state.activeThresholdQuantiles,
          ...q
        }
      };
    }

    case "SET_THEME_TOKEN": {
      const { token, value } = action.payload || {};
      if (!token || value === undefined) return state;
      return {
        ...state,
        theme: {
          ...state.theme,
          [token]: value
        }
      };
    }

    case "RESET_FILTERS": {
      return {
        ...state,
        minFlowFilter: 0,
        cyclewaysOnly: false,
        projectsOnly: false,
        selectedEdgeId: null,
        hoveredEdgeId: null
      };
    }

    default:
      return state;
  }
}

/**
 * Creates a unidirectional store with subscriber notifications and undo/redo history.
 */
function createCicloMapStore(initialState = initialCicloMapState, reducer = cicloMapReducer) {
  let state = initialState;
  const history = [state];
  let historyIndex = 0;
  const maxHistory = 50;
  const listeners = new Set();

  function getState() {
    return state;
  }

  function dispatch(action) {
    if (!action || !action.type) return state;
    const prevState = state;
    const nextState = reducer(state, action);

    if (nextState !== prevState) {
      if (historyIndex < history.length - 1) {
        history.splice(historyIndex + 1);
      }
      history.push(nextState);
      if (history.length > maxHistory) {
        history.shift();
      } else {
        historyIndex++;
      }
      state = nextState;
      listeners.forEach((listener) => {
        try {
          listener(state, prevState, action);
        } catch (e) {
          console.error("CicloMapStore listener error:", e);
        }
      });
    }
    return state;
  }

  function subscribe(listener) {
    if (typeof listener !== "function") return () => {};
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  function undo() {
    if (historyIndex > 0) {
      const prevState = state;
      historyIndex--;
      state = history[historyIndex];
      listeners.forEach((listener) => {
        try {
          listener(state, prevState, { type: "UNDO" });
        } catch (e) {
          console.error("CicloMapStore listener error:", e);
        }
      });
      return state;
    }
    return state;
  }

  function redo() {
    if (historyIndex < history.length - 1) {
      const prevState = state;
      historyIndex++;
      state = history[historyIndex];
      listeners.forEach((listener) => {
        try {
          listener(state, prevState, { type: "REDO" });
        } catch (e) {
          console.error("CicloMapStore listener error:", e);
        }
      });
      return state;
    }
    return state;
  }

  return {
    getState,
    dispatch,
    subscribe,
    undo,
    redo
  };
}

// 3. Pure Bijective Selectors for MapLibre GL JS Style Expressions

/**
 * selectFlowLayerPaint: Generates the exact line paint specifications for flow maps.
 * Bijection from Plotly:
 * - Line color: Cycleway (#27ae60) override > YlOrRd 5-class quantile ramp > road hierarchy background.
 * - Line width: Scaled dynamically by flow (w = w_min + (flow / max_flow) * delta_w) and zoom level.
 */
function selectFlowLayerPaint(state, config = {}) {
  const theme = state?.theme || initialThemeTokens;
  const maxFlow = Math.max(1, Number(config.maxFlow) || 1000);
  const q = config.quantiles || state?.activeThresholdQuantiles || initialCicloMapState.activeThresholdQuantiles;
  const fp = theme.flowPalette;
  const rh = theme.roadHierarchy;

  const lineColorExpr = [
    "case",
    // 1. Proposed Project Infrastructure without flow
    ["all", ["==", ["get", "is_project"], true], ["<=", ["to-number", ["get", "od_flow"]], 0]], theme.projectColor,
    // 2. Existing Cycleway without flow (reference green)
    [
      "all",
      ["any", ["==", ["get", "highway"], "cycleway"], ["==", ["get", "original_highway"], "cycleway"]],
      ["<=", ["to-number", ["get", "od_flow"]], 0]
    ], theme.cyclewayColor,
    // 3. Flow > 0: Discrete 5-Quantile Step matching Legend
    [">", ["to-number", ["get", "od_flow"]], 0],
    [
      "step", ["to-number", ["get", "od_flow"]],
      fp.q1,
      q.q1, fp.q2,
      q.q2, fp.q3,
      q.q3, fp.q4,
      q.q4, fp.q5
    ],
    // 4. Flow == 0: Road Hierarchy Background
    [
      "match", ["get", "highway"],
      "motorway", rh.motorway,
      "trunk", rh.trunk,
      "primary", rh.primary,
      "secondary", rh.secondary,
      "tertiary", rh.tertiary,
      "residential", rh.residential,
      "living_street", rh.living_street,
      rh.default
    ]
  ];

  // Dynamic Flow-Scaled Width Expression conforming to Plotly's w = 1.0 + (flow / max_flow) * 4.0
  const lineWidthExpr = [
    "interpolate", ["linear"], ["zoom"],
    8, [
      "case",
      ["==", ["get", "highway"], "cycleway"], 1.4,
      [">", ["to-number", ["get", "od_flow"]], 0],
      ["+", 0.6, ["*", ["min", 1.0, ["/", ["to-number", ["get", "od_flow"]], maxFlow]], 1.8]],
      ["in", ["get", "highway"], ["literal", ["motorway", "trunk"]]], 0.8,
      ["in", ["get", "highway"], ["literal", ["primary", "secondary"]]], 0.5,
      0.3
    ],
    11, [
      "case",
      ["==", ["get", "highway"], "cycleway"], 2.2,
      [">", ["to-number", ["get", "od_flow"]], 0],
      ["+", 0.9, ["*", ["min", 1.0, ["/", ["to-number", ["get", "od_flow"]], maxFlow]], 3.5]],
      ["in", ["get", "highway"], ["literal", ["motorway", "trunk"]]], 1.4,
      ["in", ["get", "highway"], ["literal", ["primary", "secondary"]]], 0.9,
      ["==", ["get", "highway"], "tertiary"], 0.6,
      0.4
    ],
    14, [
      "case",
      ["==", ["get", "highway"], "cycleway"], 3.8,
      [">", ["to-number", ["get", "od_flow"]], 0],
      ["+", 1.5, ["*", ["min", 1.0, ["/", ["to-number", ["get", "od_flow"]], maxFlow]], 6.0]],
      ["in", ["get", "highway"], ["literal", ["motorway", "trunk"]]], 2.4,
      ["in", ["get", "highway"], ["literal", ["primary", "secondary"]]], 1.8,
      ["==", ["get", "highway"], "tertiary"], 1.3,
      0.8
    ]
  ];

  const lineOpacityExpr = [
    "case",
    ["==", ["get", "is_project"], true], 1.0,
    [
      "any",
      ["==", ["get", "highway"], "cycleway"],
      ["==", ["get", "original_highway"], "cycleway"]
    ], 0.95,
    [">", ["to-number", ["get", "od_flow"]], 0], 0.90,
    0.45 // Demoted background context
  ];

  return {
    "line-color": lineColorExpr,
    "line-width": lineWidthExpr,
    "line-opacity": lineOpacityExpr
  };
}

/**
 * selectImpedanceLayerPaint: Generates paint specifications for impedance typologies.
 */
function selectImpedanceLayerPaint(state) {
  const ip = state?.theme?.impedancePalette || initialThemeTokens.impedancePalette;

  const lineColorExpr = [
    "case",
    ["==", ["get", "is_project"], true], ip.project_new,
    [
      "match", ["get", "highway"],
      "primary", ip.primary,
      "trunk", ip.primary,
      "motorway", ip.primary,
      "secondary", ip.secondary,
      "tertiary", ip.tertiary,
      "residential", ip.residential,
      "cycleway", ip.cycleway,
      ip.default
    ]
  ];

  const lineWidthExpr = [
    "interpolate", ["linear"], ["zoom"],
    8, [
      "case",
      ["==", ["get", "is_project"], true], 1.6,
      ["==", ["get", "highway"], "cycleway"], 1.4,
      0.6
    ],
    11, [
      "case",
      ["==", ["get", "is_project"], true], 2.8,
      ["==", ["get", "highway"], "cycleway"], 2.2,
      1.0
    ],
    14, [
      "case",
      ["==", ["get", "is_project"], true], 4.2,
      ["==", ["get", "highway"], "cycleway"], 3.5,
      1.8
    ]
  ];

  return {
    "line-color": lineColorExpr,
    "line-width": lineWidthExpr,
    "line-opacity": 0.85
  };
}

/**
 * selectDeltaLayerPaint: Generates paint specifications for bipolar delta flow maps.
 */
function selectDeltaLayerPaint(state, config = {}) {
  const dp = state?.theme?.deltaPalette || initialThemeTokens.deltaPalette;
  const maxDelta = Math.max(1, Number(config.maxDelta) || 100);
  const q1 = Math.round(maxDelta * 0.15);
  const q2 = Math.round(maxDelta * 0.40);
  const q3 = Math.round(maxDelta * 0.70);
  const q4 = Math.round(maxDelta);

  const lineColorExpr = [
    "step", ["get", "delta_flow"],
    dp.severe_neg, -q3,
    dp.mod_neg,    -q2,
    dp.mild_neg,   -q1,
    dp.min_neg,    0,
    dp.neutral,    1,
    dp.min_pos,    q1,
    dp.mild_pos,   q2,
    dp.mod_pos,    q3,
    dp.severe_pos
  ];

  const lineWidthExpr = [
    "interpolate", ["linear"], ["zoom"],
    8, [
      "+", 0.6,
      ["*", ["min", 1.0, ["/", ["abs", ["get", "delta_flow"]], maxDelta]], 1.8]
    ],
    11, [
      "+", 0.9,
      ["*", ["min", 1.0, ["/", ["abs", ["get", "delta_flow"]], maxDelta]], 3.5]
    ],
    14, [
      "+", 1.5,
      ["*", ["min", 1.0, ["/", ["abs", ["get", "delta_flow"]], maxDelta]], 5.5]
    ]
  ];

  return {
    "line-color": lineColorExpr,
    "line-width": lineWidthExpr,
    "line-opacity": [
      "case",
      ["==", ["get", "delta_flow"], 0], 0.0,
      0.90
    ]
  };
}

/**
 * selectEdgePopupHtml: Pure formatted HTML tooltip for interactive hover / click inspection.
 */
function selectEdgePopupHtml(properties) {
  if (!properties) return "";
  const edgeId = properties.edge_id ?? "N/A";
  const highway = properties.highway ?? "unclassified";
  const origHw = properties.original_highway ?? highway;
  const flow = Number(properties.od_flow ?? 0).toFixed(1);
  const impedance = properties.impedance !== undefined ? Number(properties.impedance).toFixed(3) : "N/A";
  const isProj = Boolean(properties.is_project);
  const projId = properties.project_id ? String(properties.project_id) : (isProj ? "Proposed" : "None");

  const badgeColor = isProj ? "#e67e22" : (highway === "cycleway" ? "#27ae60" : "#4a5568");
  const badgeText = isProj ? "PROPOSED PROJECT" : (highway === "cycleway" ? "CYCLEWAY" : highway.toUpperCase());

  return `
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 12px; color: #1a202c; line-height: 1.4; padding: 2px;">
      <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e2e8f0; padding-bottom: 5px; margin-bottom: 6px;">
        <span style="font-weight: 700; color: #2d3748;">Edge #${edgeId}</span>
        <span style="background-color: ${badgeColor}; color: #ffffff; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; text-transform: uppercase;">
          ${badgeText}
        </span>
      </div>
      <table style="width: 100%; border-collapse: collapse; font-size: 11px;">
        <tr>
          <td style="color: #718096; padding: 2px 0;">Highway:</td>
          <td style="font-weight: 600; text-align: right;">${highway}</td>
        </tr>
        ${origHw !== highway ? `
        <tr>
          <td style="color: #718096; padding: 2px 0;">Original:</td>
          <td style="font-style: italic; text-align: right;">${origHw}</td>
        </tr>` : ""}
        <tr>
          <td style="color: #718096; padding: 2px 0;">OD Flow:</td>
          <td style="font-weight: 700; color: #c53030; text-align: right;">${flow} trips</td>
        </tr>
        <tr>
          <td style="color: #718096; padding: 2px 0;">Impedance:</td>
          <td style="font-weight: 500; text-align: right;">${impedance}</td>
        </tr>
        ${isProj ? `
        <tr>
          <td style="color: #718096; padding: 2px 0;">Project ID:</td>
          <td style="font-weight: 600; color: #d69e2e; text-align: right;">${projId}</td>
        </tr>` : ""}
      </table>
    </div>
  `;
}

/**
 * selectDeltaPopupHtml: HTML tooltip for delta flow inspection.
 */
function selectDeltaPopupHtml(properties) {
  if (!properties) return "";
  const edgeId = properties.edge_id ?? "N/A";
  const delta = Number(properties.delta_flow ?? 0).toFixed(1);
  const current = Number(properties.flow_current ?? 0).toFixed(1);
  const baseline = Number(properties.flow_baseline ?? 0).toFixed(1);
  const isProj = Boolean(properties.is_project);
  const deltaColor = Number(delta) >= 0 ? "#2166ac" : "#b2182b";
  const sign = Number(delta) > 0 ? "+" : "";

  return `
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 12px; color: #1a202c; line-height: 1.4; padding: 2px;">
      <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e2e8f0; padding-bottom: 5px; margin-bottom: 6px;">
        <span style="font-weight: 700; color: #2d3748;">Edge #${edgeId}</span>
        <span style="color: ${deltaColor}; font-weight: 800; font-size: 13px;">${sign}${delta}</span>
      </div>
      <table style="width: 100%; border-collapse: collapse; font-size: 11px;">
        <tr>
          <td style="color: #718096; padding: 2px 0;">Current Flow:</td>
          <td style="font-weight: 600; text-align: right;">${current}</td>
        </tr>
        <tr>
          <td style="color: #718096; padding: 2px 0;">Baseline Flow:</td>
          <td style="font-weight: 600; text-align: right;">${baseline}</td>
        </tr>
        ${isProj ? `
        <tr>
          <td style="color: #718096; padding: 2px 0;">Status:</td>
          <td style="font-weight: 700; color: #e67e22; text-align: right;">PROPOSED PROJECT</td>
        </tr>` : ""}
      </table>
    </div>
  `;
}

/**
 * selectFlowLegendItems: Returns items for rendering the Plotly-bijective legend.
 */
function selectFlowLegendItems(state, config = {}) {
  const theme = state?.theme || initialThemeTokens;
  const fp = theme.flowPalette;
  const q = config.quantiles || state?.activeThresholdQuantiles || initialCicloMapState.activeThresholdQuantiles;

  return [
    { label: "Existing Cycleway", color: theme.cyclewayColor, width: 3 },
    { label: `Flow ≤ ${q.q1}`, color: fp.q1, width: 1.5 },
    { label: `Flow ${q.q1} – ${q.q2}`, color: fp.q2, width: 2.0 },
    { label: `Flow ${q.q2} – ${q.q3}`, color: fp.q3, width: 2.5 },
    { label: `Flow ${q.q3} – ${q.q4}`, color: fp.q4, width: 3.2 },
    { label: `Flow > ${q.q4}`, color: fp.q5, width: 4.0 },
    { label: "Proposed Project", color: theme.projectColor, width: 3, dashed: true }
  ];
}

/**
 * selectBikelanesLayerPaint: Generates paint for dedicated bikelanes-only flow map.
 * Conforms to ADR 0003: synchronized network quantiles with sequential green ramp.
 */
function selectBikelanesLayerPaint(state, config = {}) {
  const theme = state?.theme || initialThemeTokens;
  const bp = theme.bikelanePalette;
  const q = config.quantiles || state?.activeThresholdQuantiles || initialCicloMapState.activeThresholdQuantiles;
  const rh = theme.roadHierarchy;

  const lineColorExpr = [
    "case",
    // Cycleways with flow: 5-class sequential green steps matching legend
    [
      "all",
      ["any", ["==", ["get", "highway"], "cycleway"], ["==", ["get", "original_highway"], "cycleway"]],
      [">", ["to-number", ["get", "od_flow"]], 0]
    ],
    [
      "step", ["to-number", ["get", "od_flow"]],
      bp[0],
      q.q1, bp[1],
      q.q2, bp[2],
      q.q3, bp[3],
      q.q4, bp[4]
    ],
    // Cycleways with 0 flow: soft light-green reference
    ["any", ["==", ["get", "highway"], "cycleway"], ["==", ["get", "original_highway"], "cycleway"]],
    theme.existingCyclewayBg,
    // Background streets: demoted soft gray
    "#dcdfe3"
  ];

  const lineWidthExpr = [
    "interpolate", ["linear"], ["zoom"],
    8, [
      "case",
      ["any", ["==", ["get", "highway"], "cycleway"], ["==", ["get", "original_highway"], "cycleway"]], 1.8,
      ["in", ["get", "highway"], ["literal", ["motorway", "trunk"]]], 0.8,
      0.3
    ],
    11, [
      "case",
      ["any", ["==", ["get", "highway"], "cycleway"], ["==", ["get", "original_highway"], "cycleway"]], 3.0,
      ["in", ["get", "highway"], ["literal", ["motorway", "trunk"]]], 1.4,
      0.5
    ],
    14, [
      "case",
      ["any", ["==", ["get", "highway"], "cycleway"], ["==", ["get", "original_highway"], "cycleway"]], 4.5,
      ["in", ["get", "highway"], ["literal", ["motorway", "trunk"]]], 2.2,
      0.8
    ]
  ];

  const lineOpacityExpr = [
    "case",
    ["any", ["==", ["get", "highway"], "cycleway"], ["==", ["get", "original_highway"], "cycleway"]], 0.95,
    0.30
  ];

  return {
    "line-color": lineColorExpr,
    "line-width": lineWidthExpr,
    "line-opacity": lineOpacityExpr
  };
}

/**
 * selectProjectPerformanceLayerPaint: Generates paint for Project Performance Map.
 * Renders proposed project segments into 5 usage tiers (Local to Strategic Artery)
 * and existing cycleways in light blue (#4fa8e3).
 */
function selectProjectPerformanceLayerPaint(state, config = {}) {
  const theme = state?.theme || initialThemeTokens;
  const pp = theme.performancePalette;
  const q = config.quantiles || state?.activeThresholdQuantiles || initialCicloMapState.activeThresholdQuantiles;

  const lineColorExpr = [
    "case",
    // 1. Proposed Project Corridors: 5-class usage ramp
    ["==", ["get", "is_project"], true],
    [
      "step", ["to-number", ["get", "od_flow"]],
      pp[0],
      q.q1, pp[1],
      q.q2, pp[2],
      q.q3, pp[3],
      q.q4, pp[4]
    ],
    // 2. Existing Non-Project Cycleways: Light Blue continuous reference trace
    ["any", ["==", ["get", "highway"], "cycleway"], ["==", ["get", "original_highway"], "cycleway"]],
    theme.existingCyclewayPerformance,
    // 3. Background street hierarchy
    "#dcdfe3"
  ];

  const lineWidthExpr = [
    "interpolate", ["linear"], ["zoom"],
    8, [
      "case",
      ["==", ["get", "is_project"], true], 2.2,
      ["any", ["==", ["get", "highway"], "cycleway"], ["==", ["get", "original_highway"], "cycleway"]], 1.4,
      0.3
    ],
    11, [
      "case",
      ["==", ["get", "is_project"], true], 3.5,
      ["any", ["==", ["get", "highway"], "cycleway"], ["==", ["get", "original_highway"], "cycleway"]], 2.0,
      0.5
    ],
    14, [
      "case",
      ["==", ["get", "is_project"], true], 5.0,
      ["any", ["==", ["get", "highway"], "cycleway"], ["==", ["get", "original_highway"], "cycleway"]], 3.0,
      0.8
    ]
  ];

  const lineOpacityExpr = [
    "case",
    ["==", ["get", "is_project"], true], 1.0,
    ["any", ["==", ["get", "highway"], "cycleway"], ["==", ["get", "original_highway"], "cycleway"]], 0.85,
    0.30
  ];

  return {
    "line-color": lineColorExpr,
    "line-width": lineWidthExpr,
    "line-opacity": lineOpacityExpr
  };
}

/**
 * selectH3LayerPaint: Generates fill paint for H3 Hexagonal Travel Demand.
 * Log-scaled continuous density matching Plotly np.log1p(val) / np.log1p(p95).
 */
function selectH3LayerPaint(state, config = {}) {
  const theme = state?.theme || initialThemeTokens;
  const purpose = config.purpose || "work";
  const palette = theme.purposePalettes[purpose] || theme.purposePalettes.default;
  const col = config.column || `trips_${purpose}`;
  const p95 = Math.max(1, Number(config.p95) || 100);
  const logP95 = Math.log1p(p95);

  const fillColorExpr = [
    "interpolate", ["linear"],
    ["min", 1.0, ["/", ["ln", ["+", 1, ["max", 0, ["get", col]]]], logP95]],
    0.00, palette[0],
    0.25, palette[1],
    0.50, palette[2],
    0.75, palette[3],
    1.00, palette[4]
  ];

  return {
    "fill-color": fillColorExpr,
    "fill-opacity": [
      "case",
      ["<=", ["get", col], 0], 0.0,
      0.40
    ],
    "fill-outline-color": "rgba(0,0,0,0.08)"
  };
}

/**
 * selectPerformancePopupHtml: Formats popup for Project Performance inspection.
 */
function selectPerformancePopupHtml(properties, totalTrips = 1.0) {
  if (!properties) return "";
  const flow = Number(properties.od_flow ?? 0);
  const trips = Math.max(1, Number(totalTrips) || 1);
  const pcr = ((flow / trips) * 100).toFixed(2);
  const isProj = Boolean(properties.is_project);
  const projId = properties.project_id || (isProj ? "Recommended Corridor" : "Existing Cycleway");
  const badgeColor = isProj ? "#1b5e20" : "#4fa8e3";
  const badgeText = isProj ? "PROJECT SEGMENT" : "EXISTING CYCLEWAY";

  return `
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 12px; color: #1a202c; padding: 2px;">
      <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e2e8f0; padding-bottom: 5px; margin-bottom: 6px;">
        <span style="font-weight: 700; color: #2d3748;">${projId}</span>
        <span style="background-color: ${badgeColor}; color: #ffffff; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 600;">
          ${badgeText}
        </span>
      </div>
      <table style="width: 100%; border-collapse: collapse; font-size: 11px;">
        <tr>
          <td style="color: #718096; padding: 2px 0;">Segment Load:</td>
          <td style="font-weight: 700; text-align: right; color: #1b5e20;">${flow.toFixed(0)} trips</td>
        </tr>
        ${isProj ? `
        <tr>
          <td style="color: #718096; padding: 2px 0;">Capture (PCR):</td>
          <td style="font-weight: 700; text-align: right; color: #2b6cb0;">${pcr}%</td>
        </tr>` : ""}
      </table>
    </div>
  `;
}

/**
 * selectH3PopupHtml: Formats tooltip for H3 hexagon demographic inspection.
 */
function selectH3PopupHtml(properties, activePurpose = "work") {
  if (!properties) return "";
  const h3 = properties.h3_index || "Hexagon";
  const col = `trips_${activePurpose}`;
  const trips = Number(properties[col] ?? properties.od_flow ?? 0).toFixed(1);
  const pop = Number(properties.pop_total ?? 0).toFixed(0);
  const purposeName = activePurpose.replace("_", " ").toUpperCase();

  return `
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 12px; color: #1a202c; padding: 2px;">
      <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e2e8f0; padding-bottom: 5px; margin-bottom: 6px;">
        <span style="font-weight: 700; color: #2d3748;">Hex #${h3.slice(-6)}</span>
        <span style="background-color: #3182ce; color: #ffffff; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 600;">
          ${purposeName}
        </span>
      </div>
      <table style="width: 100%; border-collapse: collapse; font-size: 11px;">
        <tr>
          <td style="color: #718096; padding: 2px 0;">Trips Demand:</td>
          <td style="font-weight: 700; text-align: right; color: #2b6cb0;">${trips}</td>
        </tr>
        <tr>
          <td style="color: #718096; padding: 2px 0;">Total Pop:</td>
          <td style="font-weight: 500; text-align: right;">${pop}</td>
        </tr>
      </table>
    </div>
  `;
}

/**
 * selectPerformanceLegendItems: Legend for project performance tiers.
 */
function selectPerformanceLegendItems(quantiles) {
  const q = quantiles || initialCicloMapState.activeThresholdQuantiles;
  return [
    { label: "Existing Cycleway", color: "#4fa8e3", width: 2.5 },
    { label: `Local Use (≤ ${q.q1})`, color: "#c8e6c9", width: 2.5 },
    { label: `Connector Use (${q.q1}–${q.q2})`, color: "#81c784", width: 3.0 },
    { label: `Trunk Use (${q.q2}–${q.q3})`, color: "#4caf50", width: 3.5 },
    { label: `Critical Use (${q.q3}–${q.q4})`, color: "#2e7d32", width: 4.0 },
    { label: `Strategic Artery (>${q.q4})`, color: "#1b5e20", width: 5.0 }
  ];
}

/**
 * selectBikelanesLegendItems: Legend for dedicated cycleway flow map.
 */
function selectBikelanesLegendItems(quantiles) {
  const q = quantiles || initialCicloMapState.activeThresholdQuantiles;
  return [
    { label: `Cycleway Flow ≤ ${q.q1}`, color: "#c8e6c9", width: 3.0 },
    { label: `Cycleway Flow ${q.q1}–${q.q2}`, color: "#81c784", width: 3.0 },
    { label: `Cycleway Flow ${q.q2}–${q.q3}`, color: "#4caf50", width: 3.0 },
    { label: `Cycleway Flow ${q.q3}–${q.q4}`, color: "#2e7d32", width: 3.0 },
    { label: `Cycleway Flow > ${q.q4}`, color: "#1b5e20", width: 3.0 },
    { label: "Existing Cycleway (No Flow)", color: "#b0d5b4", width: 2.0 }
  ];
}

// Universal Module Definition
const CicloMapReducer = {
  initialThemeTokens,
  initialCicloMapState,
  cicloMapReducer,
  createCicloMapStore,
  selectFlowLayerPaint,
  selectBikelanesLayerPaint,
  selectProjectPerformanceLayerPaint,
  selectH3LayerPaint,
  selectImpedanceLayerPaint,
  selectDeltaLayerPaint,
  selectEdgePopupHtml,
  selectPerformancePopupHtml,
  selectH3PopupHtml,
  selectDeltaPopupHtml,
  selectFlowLegendItems,
  selectPerformanceLegendItems,
  selectBikelanesLegendItems
};

if (typeof module !== "undefined" && module.exports) {
  module.exports = CicloMapReducer;
  module.exports.default = CicloMapReducer;
  module.exports.initialThemeTokens = initialThemeTokens;
  module.exports.initialCicloMapState = initialCicloMapState;
  module.exports.cicloMapReducer = cicloMapReducer;
  module.exports.createCicloMapStore = createCicloMapStore;
  module.exports.selectFlowLayerPaint = selectFlowLayerPaint;
  module.exports.selectBikelanesLayerPaint = selectBikelanesLayerPaint;
  module.exports.selectProjectPerformanceLayerPaint = selectProjectPerformanceLayerPaint;
  module.exports.selectH3LayerPaint = selectH3LayerPaint;
  module.exports.selectImpedanceLayerPaint = selectImpedanceLayerPaint;
  module.exports.selectDeltaLayerPaint = selectDeltaLayerPaint;
  module.exports.selectEdgePopupHtml = selectEdgePopupHtml;
  module.exports.selectPerformancePopupHtml = selectPerformancePopupHtml;
  module.exports.selectH3PopupHtml = selectH3PopupHtml;
  module.exports.selectDeltaPopupHtml = selectDeltaPopupHtml;
  module.exports.selectFlowLegendItems = selectFlowLegendItems;
  module.exports.selectPerformanceLegendItems = selectPerformanceLegendItems;
  module.exports.selectBikelanesLegendItems = selectBikelanesLegendItems;
}

if (typeof window !== "undefined") {
  window.CicloMapReducer = CicloMapReducer;
}
if (typeof globalThis !== "undefined") {
  globalThis.CicloMapReducer = CicloMapReducer;
}
