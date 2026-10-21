/**
 * test_ciclo_map_reducer.js
 * Headless Node.js Unit Test Suite for ciclo_map_reducer.js
 */

const assert = require("assert");
const {
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
} = require("../app/core/cartography/ciclo_map_reducer.js");

console.log("Running Headless Tests for ciclo_map_reducer.js...\n");

// Test 1: Reducer initial state and unknown action immutability
{
  const state = cicloMapReducer(undefined, { type: "@@INIT" });
  assert.strictEqual(state.viewMode, "flow");
  assert.strictEqual(state.minFlowFilter, 0);
  assert.strictEqual(state.cyclewaysOnly, false);
  assert.strictEqual(state.projectsOnly, false);
  assert.strictEqual(state.selectedEdgeId, null);

  const unchanged = cicloMapReducer(state, { type: "UNKNOWN_ACTION" });
  assert.strictEqual(state, unchanged);
  console.log("✔ Test 1 Passed: Reducer initialization and unknown action immutability");
}

// Test 2: View mode transitions
{
  let state = cicloMapReducer(initialCicloMapState, {
    type: "SET_VIEW_MODE",
    payload: { viewMode: "impedance" }
  });
  assert.strictEqual(state.viewMode, "impedance");

  // Setting same viewMode returns referentially equal state
  const same = cicloMapReducer(state, {
    type: "SET_VIEW_MODE",
    payload: { viewMode: "impedance" }
  });
  assert.strictEqual(state, same);
  console.log("✔ Test 2 Passed: View mode transitions with referential equality");
}

// Test 3: Filters (minFlow, cyclewaysOnly, projectsOnly)
{
  let state = cicloMapReducer(initialCicloMapState, {
    type: "SET_MIN_FLOW_FILTER",
    payload: { minFlow: 25.5 }
  });
  assert.strictEqual(state.minFlowFilter, 25.5);

  state = cicloMapReducer(state, { type: "TOGGLE_CYCLEWAYS_ONLY" });
  assert.strictEqual(state.cyclewaysOnly, true);
  assert.strictEqual(state.projectsOnly, false);

  state = cicloMapReducer(state, { type: "TOGGLE_PROJECTS_ONLY" });
  assert.strictEqual(state.projectsOnly, true);
  assert.strictEqual(state.cyclewaysOnly, false);

  state = cicloMapReducer(state, { type: "RESET_FILTERS" });
  assert.strictEqual(state.minFlowFilter, 0);
  assert.strictEqual(state.cyclewaysOnly, false);
  assert.strictEqual(state.projectsOnly, false);
  console.log("✔ Test 3 Passed: Interactive filters toggle and reset");
}

// Test 4: Store creation, subscriber notifications, undo/redo
{
  const store = createCicloMapStore();
  let callCount = 0;
  let lastAction = null;

  const unsubscribe = store.subscribe((curr, prev, action) => {
    callCount++;
    lastAction = action;
  });

  store.dispatch({ type: "SELECT_EDGE", payload: { edgeId: 4210 } });
  assert.strictEqual(store.getState().selectedEdgeId, 4210);
  assert.strictEqual(callCount, 1);
  assert.strictEqual(lastAction.type, "SELECT_EDGE");

  store.dispatch({ type: "SELECT_EDGE", payload: { edgeId: 9999 } });
  assert.strictEqual(store.getState().selectedEdgeId, 9999);
  assert.strictEqual(callCount, 2);

  // Undo
  store.undo();
  assert.strictEqual(store.getState().selectedEdgeId, 4210);
  assert.strictEqual(callCount, 3);

  // Redo
  store.redo();
  assert.strictEqual(store.getState().selectedEdgeId, 9999);
  assert.strictEqual(callCount, 4);

  unsubscribe();
  store.dispatch({ type: "RESET_FILTERS" });
  assert.strictEqual(callCount, 4); // Not called after unsubscribe
  console.log("✔ Test 4 Passed: Store subscription, dispatch, and undo/redo history");
}

// Test 5: Bijective Paint Selectors for MapLibre
{
  const paint = selectFlowLayerPaint(initialCicloMapState, {
    maxFlow: 500,
    quantiles: { q1: 10, q2: 50, q3: 150, q4: 300, q5: 500 }
  });

  assert.ok(paint["line-color"]);
  assert.ok(paint["line-width"]);
  assert.ok(paint["line-opacity"]);

  // Verify ColorBrewer YlOrRd colors are present in line-color expression
  const colorJson = JSON.stringify(paint["line-color"]);
  assert.ok(colorJson.includes("#fed976"), "Q1 color missing");
  assert.ok(colorJson.includes("#feb24c"), "Q2 color missing");
  assert.ok(colorJson.includes("#fd8d3c"), "Q3 color missing");
  assert.ok(colorJson.includes("#f03b20"), "Q4 color missing");
  assert.ok(colorJson.includes("#bd0026"), "Q5 color missing");
  assert.ok(colorJson.includes("#27ae60"), "Cycleway color missing");

  // Verify dynamic width expression contains interpolation and flow scaling
  const widthJson = JSON.stringify(paint["line-width"]);
  assert.ok(widthJson.includes("interpolate"), "Interpolation missing in line-width");
  assert.ok(widthJson.includes("od_flow"), "od_flow missing in line-width");
  assert.ok(widthJson.includes("500"), "maxFlow missing in line-width divisor");

  console.log("✔ Test 5 Passed: Flow layer MapLibre paint expressions with flow-scaled width");
}

// Test 6: Impedance and Delta Selectors
{
  const impPaint = selectImpedanceLayerPaint(initialCicloMapState);
  assert.ok(impPaint["line-color"]);
  assert.ok(JSON.stringify(impPaint["line-color"]).includes("#e91e63")); // Primary
  assert.ok(JSON.stringify(impPaint["line-color"]).includes("#27ae60")); // Cycleway

  const deltaPaint = selectDeltaLayerPaint(initialCicloMapState, { maxDelta: 250 });
  assert.ok(deltaPaint["line-color"]);
  assert.ok(JSON.stringify(deltaPaint["line-color"]).includes("#b2182b")); // Severe decrease
  assert.ok(JSON.stringify(deltaPaint["line-color"]).includes("#2166ac")); // Severe increase
  console.log("✔ Test 6 Passed: Impedance and Delta layer paint specifications");
}

// Test 7: Popup HTML Selectors
{
  const popupHtml = selectEdgePopupHtml({
    edge_id: 88412,
    highway: "cycleway",
    original_highway: "residential",
    od_flow: 142.8,
    impedance: 1.05,
    is_project: true,
    project_id: "CICLO-SANT-01"
  });

  assert.ok(popupHtml.includes("Edge #88412"));
  assert.ok(popupHtml.includes("cycleway"));
  assert.ok(popupHtml.includes("residential"));
  assert.ok(popupHtml.includes("142.8 trips"));
  assert.ok(popupHtml.includes("CICLO-SANT-01"));

  const deltaHtml = selectDeltaPopupHtml({
    edge_id: 88412,
    delta_flow: -45.2,
    flow_current: 10.0,
    flow_baseline: 55.2
  });
  assert.ok(deltaHtml.includes("-45.2"));
  assert.ok(deltaHtml.includes("#b2182b")); // Negative color
  console.log("✔ Test 7 Passed: Tooltip popup HTML generators");
}

// Test 8: Legend Selectors
{
  const items = selectFlowLegendItems(initialCicloMapState, {
    quantiles: { q1: 5, q2: 20, q3: 80, q4: 250, q5: 800 }
  });
  assert.strictEqual(items.length, 7);
  assert.strictEqual(items[0].label, "Existing Cycleway");
  assert.strictEqual(items[1].label, "Flow ≤ 5");
  assert.strictEqual(items[5].label, "Flow > 250");
  console.log("✔ Test 8 Passed: Bijective Flow legend items generator");
}

// Test 9: Bikelanes and Project Performance Selectors
{
  const bikePaint = selectBikelanesLayerPaint(initialCicloMapState, {
    quantiles: { q1: 10, q2: 50, q3: 150, q4: 300, q5: 500 }
  });
  assert.ok(bikePaint["line-color"]);
  assert.ok(JSON.stringify(bikePaint["line-color"]).includes("#1b5e20")); // Peak green

  const perfPaint = selectProjectPerformanceLayerPaint(initialCicloMapState, {
    quantiles: { q1: 10, q2: 50, q3: 150, q4: 300, q5: 500 }
  });
  assert.ok(perfPaint["line-color"]);
  assert.ok(JSON.stringify(perfPaint["line-color"]).includes("#4fa8e3")); // Existing cycleway light blue

  const perfPopup = selectPerformancePopupHtml({
    project_id: "CICLO-SANT-01",
    od_flow: 2500,
    is_project: true
  }, 100000);
  assert.ok(perfPopup.includes("CICLO-SANT-01"));
  assert.ok(perfPopup.includes("2.50%")); // PCR capture
  console.log("✔ Test 9 Passed: Bikelanes and Project Performance (PCR %) selectors");
}

// Test 10: H3 Hexagonal Density Selectors
{
  const h3Paint = selectH3LayerPaint(initialCicloMapState, {
    purpose: "work",
    column: "trips_work",
    p95: 1500
  });
  assert.ok(h3Paint["fill-color"]);
  assert.ok(JSON.stringify(h3Paint["fill-color"]).includes("interpolate"));
  assert.ok(JSON.stringify(h3Paint["fill-color"]).includes("trips_work"));

  const h3Popup = selectH3PopupHtml({
    h3_index: "884f094285fffff",
    trips_work: 420.5,
    pop_total: 12000
  }, "work");
  assert.ok(h3Popup.includes("420.5"));
  assert.ok(h3Popup.includes("12000"));
  assert.ok(h3Popup.includes("WORK"));
  console.log("✔ Test 10 Passed: H3 Hexagonal Travel Demand paint and popup selectors");
}

console.log("\n=========================================");
console.log("ALL 10 UNIT TESTS PASSED SUCCESSFULLY! ✔");
console.log("=========================================\n");
