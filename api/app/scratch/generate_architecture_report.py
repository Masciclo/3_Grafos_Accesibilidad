import os
import time
import tempfile
import subprocess

def main():
    temp_dir = tempfile.gettempdir()
    timestamp = int(time.time())
    report_filename = f"architecture-review-{timestamp}.html"
    report_path = os.path.join(temp_dir, report_filename)

    html_content = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Architecture review — +Ciclo Delta Engine</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
      mermaid.initialize({ startOnLoad: true, theme: "neutral", securityLevel: "loose" });
    </script>
    <style>
      .seam { stroke-dasharray: 4 4; }
      .leak { stroke: #dc2626; }
      .deep { background: linear-gradient(135deg, #0f172a, #1e293b); }
    </style>
  </head>
  <body class="bg-stone-50 text-slate-900 font-sans antialiased">
    <main class="max-w-5xl mx-auto px-6 py-12 space-y-12">
      
      <!-- Header -->
      <header class="border-b border-slate-200 pb-6">
        <h1 class="text-4xl font-bold font-serif text-slate-900 tracking-tight">+Ciclo Architecture Review</h1>
        <p class="text-sm text-slate-500 mt-2">Date: 2026-07-16 | Scope: Scenario Workflows & Topological Refactoring Seams</p>
        
        <!-- Legend -->
        <div class="mt-6 flex flex-wrap gap-6 text-xs text-slate-600 bg-white p-4 rounded-lg border border-slate-100">
          <div class="flex items-center gap-2">
            <span class="w-4 h-4 bg-slate-100 border border-slate-300 rounded block"></span>
            <span>Module</span>
          </div>
          <div class="flex items-center gap-2">
            <span class="w-4 h-4 bg-slate-900 rounded block"></span>
            <span>Deep Module</span>
          </div>
          <div class="flex items-center gap-2">
            <span class="w-6 border-t-2 border-dashed border-slate-400 block"></span>
            <span>Interface / Seam</span>
          </div>
          <div class="flex items-center gap-2">
            <span class="w-4 h-4 bg-emerald-100 text-emerald-800 font-bold px-1 rounded block text-center leading-3" style="font-size: 8px;">S</span>
            <span>Strong Recommendation</span>
          </div>
        </div>
      </header>

      <!-- Candidates Section -->
      <section id="candidates" class="space-y-12">
        <article class="bg-white p-8 rounded-xl border border-slate-200 shadow-sm space-y-6">
          <div class="flex justify-between items-start">
            <div>
              <h2 class="text-2xl font-bold font-serif text-slate-900">1. Introduce a Polymorphic Refactor Seam</h2>
              <p class="text-sm text-slate-400 mt-1">Refactoring Strategy & Workflow Decoupling</p>
            </div>
            <div class="flex gap-2">
              <span class="bg-emerald-100 text-emerald-800 text-xs font-semibold px-2.5 py-1 rounded">Strong</span>
              <span class="bg-slate-100 text-slate-800 text-xs font-semibold px-2.5 py-1 rounded">ports & adapters</span>
            </div>
          </div>

          <div class="text-sm text-slate-600">
            <strong>Files:</strong> 
            <span class="font-mono bg-slate-50 px-1.5 py-0.5 rounded text-xs">api/app/core/network_refactor.py</span>, 
            <span class="font-mono bg-slate-50 px-1.5 py-0.5 rounded text-xs">api/app/core/tasks.py</span>, 
            <span class="font-mono bg-slate-50 px-1.5 py-0.5 rounded text-xs">api/app/main.py</span>
          </div>

          <!-- Before / After Diagram -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <!-- Before -->
            <div class="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">Before: Shallow Branching</h3>
              <pre class="mermaid bg-slate-50">
flowchart TD
    MAIN[main.py] -->|args & scenario_id| REFACTOR[SpatialRefactorAdapter]
    REFACTOR -->|if scenario_id starts with rec_| BYPASS[Bypass / SQL Stage 2 Union]
    REFACTOR -->|if projects_input & not rec_| SUTURA[Iterative Shatter & Sutura]
    REFACTOR -->|else| BASE[Pass-through]
    
    style REFACTOR fill:#fff,stroke:#dc2626,stroke-width:2px;
    style BYPASS fill:#fef08a,stroke:#333;
    style SUTURA fill:#fef08a,stroke:#333;
    style BASE fill:#fef08a,stroke:#333;
              </pre>
            </div>
            
            <!-- After -->
            <div class="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">After: Deep Seam & Strategy Adapters</h3>
              <pre class="mermaid bg-slate-50">
flowchart TD
    MAIN[main.py] -->|ScenarioConfig| REFACTOR[SpatialRefactorAdapter: Deep Seam]
    REFACTOR -.-> STRATEGY{RefactorStrategy: Interface}
    
    STRATEGY -->|Adapter A| BASE_AD[BaseScenarioStrategy]
    STRATEGY -->|Adapter B| SUTURA_AD[SuturaRefactorStrategy]
    STRATEGY -->|Adapter C| REC_AD[RecommendationStrategy]
    
    style REFACTOR fill:#0f172a,stroke:#333,stroke-width:2px;
    style STRATEGY stroke-dasharray: 5 5,stroke-width:2px;
    style BASE_AD fill:#93c5fd,stroke:#333;
    style SUTURA_AD fill:#93c5fd,stroke:#333;
    style REC_AD fill:#93c5fd,stroke:#333;
              </pre>
            </div>
          </div>

          <div class="space-y-4 pt-4 border-t border-slate-100">
            <p class="text-slate-700">
              <strong>Problem:</strong> The refactoring module (<code class="font-mono bg-slate-50 px-1 rounded">SpatialRefactorAdapter</code>) is shallow. Its interface accepts generic configuration objects, leaking workflow-type checks (<code class="font-mono bg-slate-50 px-1 rounded">startswith("rec_")</code>) and branching logic directly inside the refactor controller. This mixes the three workflows (Base, Manual, and Algorithmic) into one file, harming locality and making strategy-specific tests hard to write.
            </p>
            <p class="text-slate-700">
              <strong>Solution:</strong> Establish a polymorphic seam (<code class="font-mono bg-slate-50 px-1 rounded">RefactorStrategy</code>) with three concrete Strategy Adapters. This encapsulates the workflow logic inside dedicated modules, providing depth and high leverage to the scenario orchestrator.
            </p>
            <div>
              <strong class="text-slate-900 block mb-2">Key Wins:</strong>
              <ul class="list-disc pl-5 text-sm text-slate-600 space-y-1">
                <li><strong>Locality</strong>: Strategy details isolated.</li>
                <li><strong>Leverage</strong>: Pipeline calls one clean interface.</li>
                <li><strong>Testability</strong>: Mock/Test strategies in isolation.</li>
                <li><strong>Interface</strong>: Bypasses string-checking scenario ID logic.</li>
              </ul>
            </div>
          </div>
        </article>
      </section>

      <!-- Top Recommendation -->
      <section id="top-recommendation" class="bg-slate-900 text-white p-8 rounded-xl space-y-4">
        <h2 class="text-xl font-bold font-serif">Top Recommendation: Deepen the Refactoring Seam</h2>
        <p class="text-sm text-slate-300">
          Refactoring the <code class="font-mono bg-slate-800 text-slate-200 px-1.5 py-0.5 rounded text-xs">SpatialRefactorAdapter</code> to use a Strategy Seam provides the highest leverage. By isolating the three workflows (Base, Manual Project, and Algorithmic Discovery), we separate the SQL union injection of recommendations from the complex geometry sutures of manual plans, bringing absolute locality to maintenance and testing.
        </p>
      </main>
    </main>
  </body>
</html>
"""

    with open(report_path, "w") as f:
        f.write(html_content)

    print(f"Architecture review HTML report generated at: {report_path}")
    
    # Open the report in the default browser based on OS (macOS: open)
    try:
        subprocess.run(["open", report_path], check=True)
        print("Successfully opened the report in your browser.")
    except Exception as e:
        print(f"Warning: Could not open the report automatically: {e}")

if __name__ == "__main__":
    main()
