# Autonomous Software Repair Pipeline for Public-Interest Software

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI Dashboard](https://img.shields.io/badge/dashboard-FastAPI%20%7C%20SSE-009688.svg)](https://fastapi.tiangolo.com/)
[![Verification Gates](https://img.shields.io/badge/verification-pytest%20%7C%20hypothesis%20%7C%20ast--mutations-brightgreen.svg)]()
[![UN SDGs](https://img.shields.io/badge/UN%20SDGs-6%20%7C%209%20%7C%2016-orange.svg)](https://sdgs.un.org/)

An end-to-end autonomous agent pipeline designed to repair critical public-interest and civic software systems (aligned with **UN SDG 6: Clean Water and Sanitation**, **UN SDG 9: Industry, Innovation, and Infrastructure**, and **UN SDG 16: Peace, Justice, and Strong Institutions**).

The system autonomously ingests unfamiliar codebases, runs in isolated environments (ephemeral Docker or subprocess virtualenvs), computes spectrum-based statistical fault localization (Ochiai metric), formulates multiple competing root-cause hypotheses, synthesizes minimal unified git diffs, and evaluates patches through a multi-layer verification gate (Regression, Hypothesis Generative Fuzzing, and AST Mutation Testing) to mathematically eliminate patch overfitting. It includes a live real-time web dashboard with SSE event streaming and automated GitHub Pull Request publishing.

---

## 🏛️ System Architecture

```
                           ┌──────────────────────────────────────────────┐
                           │    Stage 1: Secure Sandboxing & Ingestion    │
                           │   - Ephemeral Subprocess / Docker Isolation  │
                           │   - Manifest & Test Framework Detection      │
                           └──────────────────────┬───────────────────────┘
                                                  │
                                                  ▼
                           ┌──────────────────────────────────────────────┐
                           │ Stage 2: Spectrum-Based Fault Localization   │
                           │   - Per-test statement coverage tracing      │
                           │   - Statistical Ochiai Suspiciousness Scoring│
                           │   - Top-k AST Enclosing Block Extraction     │
                           └──────────────────────┬───────────────────────┘
                                                  │
                                                  ▼
                           ┌──────────────────────────────────────────────┐
                           │  Stage 3: Multi-Hypothesis Patch Synthesis   │
                           │   - Formulates 3-5 distinct root causes      │
                           │   - Selects true mechanical fault            │
                           │   - Generates minimal Unified Git Diff       │
                           │   - Gemini / OpenAI / Anthropic / Offline    │
                           └──────────────────────┬───────────────────────┘
                                                  │
                                                  ▼
                           ┌──────────────────────────────────────────────┐
                           │    Stage 4: Multi-Layer Verification Gate    │
                           │   - Gate 1: Baseline Regression (Unit Tests) │
                           │   - Gate 2: Property Fuzzing (Hypothesis)    │
                           │   - Gate 3: Mutation Testing (AST Mutants)   │
                           └──────────────────────┬───────────────────────┘
                                                  │ (Passes all 3 Gates)
                                                  ▼
                           ┌──────────────────────────────────────────────┐
                           │    Stage 5: Reviewer-Ready PR Packaging      │
                           │   - UN SDGs Impact Header & Alignment        │
                           │   - Mechanical Root Cause Explanation        │
                           │   - Line-by-Line Logic Patch Summary         │
                           │   - Multi-Layer Verification Matrix          │
                           └──────────────────────┬───────────────────────┘
                                                  │
                     ┌────────────────────────────┴───────────────────────────┐
                     ▼                                                        ▼
       ┌──────────────────────────────┐                        ┌──────────────────────────────┐
       │     Interactive Web UI       │                        │   Automated GitHub Service   │
       │  - Live SSE Event Streaming  │                        │  - Remote GitHub REST API PR │
       │  - Real-time Ochiai Heatmap  │                        │  - Local Git Feature Branch  │
       │  - Human-in-the-Loop Review  │                        │  - Automated Commit & Push   │
       └──────────────────────────────┘                        └──────────────────────────────┘
```

---

## 🔬 Core Capabilities

### 1. Mathematical Fault Localization (Ochiai SBFL)
For every executable statement $s$ across failing and passing test executions, the pipeline instruments the runtime using `coverage.py` and calculates statistical suspiciousness using the **Ochiai Metric**:

$$\text{Score}(s) = \frac{\text{Failed}(s)}{\sqrt{\text{TotalFailed} \times (\text{Failed}(s) + \text{Passed}(s))}}$$

Where:
- $\text{Failed}(s)$: Number of failing tests that executed statement $s$
- $\text{Passed}(s)$: Number of passing tests that executed statement $s$
- $\text{TotalFailed}$: Total number of failing tests in the test suite
- $\text{TotalPassed}$: Total number of passing tests in the test suite

Lines are ranked in descending order of suspiciousness. The AST context extractor extracts enclosing function definitions and structural blocks with surrounding context padding to provide targeted context to the reasoning engine.

### 2. Multi-Hypothesis Patch Synthesis
Rather than jumping to the first plausible edit, the reasoning engine is prompted to formulate **3 to 5 mutually distinct root-cause hypotheses** before writing code. This forces the agent to differentiate between:
- Symptomatic band-aids (e.g., hardcoding a special case for a failing test input)
- Incorrect type coercions
- Flawed algorithmic invariants / off-by-one errors

Supported providers:
- **Google Gemini**: `gemini-2.5-flash`, `gemini-1.5-pro` (via `google-genai`)
- **OpenAI**: `gpt-4o`, `gpt-4o-mini`, `o1`
- **Anthropic**: `claude-3-5-sonnet-20241022`
- **Mock/Deterministic**: Built-in offline mode for reproducible local benchmarking without external API keys

### 3. Multi-Layer Anti-Overfitting Verification Gates
Public-interest and civic software cannot afford "overfitted" patches where an AI model hardcodes a branch for a single failing test value. The pipeline enforces three orthogonal verification layers:

1. **Gate 1: Baseline Regression Check**  
   Applies candidate unified diff in the isolated sandbox and verifies that 100% of baseline unit tests pass.
2. **Gate 2: Generative Property-Based Testing (Hypothesis)**  
   Synthesizes and runs randomized fuzz inputs across algebraic invariants (e.g., date invertibility $T_{utc} + \text{offset} = T_{local}$, monotonicity, boundary values). If Hypothesis falsifies an invariant, the shrunk minimal counterexample is fed back into the repair loop.
3. **Gate 3: Mutation Testing (AST Mutator)**  
   Injects synthetic mutations (mutating comparison operators, binary arithmetic, boolean logic, and constants) into the patched code. Evaluates whether the test suite kills the mutants:
   
   $$\text{Mutation Score} = \frac{\text{Mutants Killed}}{\text{Total Mutants}}$$
   
   Candidate patches must satisfy the minimum mutation score threshold (default 65%) to ensure that the code is rigorously asserted and not fragile.

### 4. Real-Time Web Dashboard (FastAPI + Server-Sent Events)
The pipeline features a web dashboard served by FastAPI:
- **Live SSE Event Stream**: Streams pipeline milestones, test execution outputs, and iteration logs in real time.
- **Ochiai Suspiciousness Heatmap**: Visualizes suspicious code blocks and line scores.
- **Hypothesis Explorer**: Inspects competing root-cause hypotheses generated by the LLM.
- **Verification Gate Matrix**: Live status indicators for Regression, Hypothesis Fuzzing, and AST Mutation Testing.
- **Interactive Diff Viewer**: Highlights before/after unified git diffs with syntax styling.
- **Human-in-the-Loop Approval**: Allows maintainers to review, approve, and deploy patches.

### 5. Automated GitHub PR Publishing
With the `GitHubService` module, approved patches can be directly published:
- **Remote GitHub API**: Automatically forks/branches and opens a formal Pull Request on GitHub using `GITHUB_TOKEN`.
- **Local Git Fallback**: Creates an isolated feature branch (e.g., `fix/autonomous-repair-<timestamp>`), applies the patch, commits, and provides the branch ready for review.

---

## 📂 Public-Interest Benchmark Repositories

The project includes pre-configured, realistic civic software repositories located in [`test_repositories/`](file:///Users/mac/Desktop/git%20error%20tracker/test_repositories) and [`benchmark/`](file:///Users/mac/Desktop/git%20error%20tracker/benchmark):

| Repository | Domain & UN SDG | Mechanical Fault | Verification Focus |
| :--- | :--- | :--- | :--- |
| **`benchmark/repo`** | **SDG 16** (Public Audit) | Leap-year timezone parsing failure on Feb 29 | Property fuzzing invertibility ($T_{utc} \leftrightarrow T_{local}$) |
| **`civic-pension-calculator`** | **SDG 16** (Civil Service & Pensions) | Early retirement penalty cliff-edge deduction | Strict boundary checks & monotonic benefit scaling |
| **`disaster-supply-allocator`** | **SDG 9 / 11** (Emergency Logistics) | Priority weight normalization and integer rounding error | Multi-district rationing conservation invariant |
| **`water-quality-monitor`** | **SDG 6** (Clean Water & Sanitation) | Sensor telemetry anomaly threshold and moving average lag | Dynamic spike detection and safety alert trigger |

---

## 📁 Repository Structure

```
git error tracker/
├── autonomous_repair/              # Core Modular Pipeline Package
│   ├── __init__.py
│   ├── config.py                   # Guardrails, budgets, thresholds, API keys
│   ├── pipeline.py                 # 5-Stage Orchestrator & Event Dispatcher
│   ├── sandbox/                    # Stage 1: Sandboxing & Ingestion
│   │   ├── base.py                 # Abstract sandbox & manifest detector
│   │   ├── subprocess_venv.py      # Ephemeral subprocess virtualenv sandbox
│   │   └── docker_sandbox.py       # Ephemeral Docker container sandbox
│   ├── localization/               # Stage 2: Spectrum-Based Fault Localization
│   │   ├── coverage_tracer.py      # Per-test statement coverage tracing
│   │   ├── ochiai.py               # Ochiai formula calculator
│   │   └── context_extractor.py    # AST enclosing function/block extractor
│   ├── synthesis/                  # Stage 3: Multi-Hypothesis Synthesis
│   │   ├── diff_parser.py          # Unified diff parser & patch applier
│   │   ├── prompt_templates.py     # Prompt templates enforcing 3-5 hypotheses
│   │   └── llm_client.py           # Pluggable LLM interface (Gemini, OpenAI, Anthropic, Mock)
│   ├── verification/               # Stage 4: Multi-Layer Verification Gate
│   │   ├── regression_gate.py      # Gate 1: Baseline unit regression runner
│   │   ├── property_gate.py        # Gate 2: Hypothesis property fuzz runner
│   │   ├── mutation_gate.py        # Gate 3: AST mutation injector & score evaluator
│   │   └── verification_matrix.py  # Matrix aggregator and feedback generator
│   └── pr_generator/               # Stage 5: Reviewer PR Packaging
│       └── pr_packager.py          # Markdown PR generator
│
├── server/                         # Interactive Web Dashboard & Services
│   ├── app.py                      # FastAPI server with SSE streaming & REST API
│   ├── github_service.py           # GitHub REST API & local Git branch publishing
│   └── static/                     # Web dashboard frontend (HTML/CSS/JS)
│
├── test_repositories/              # Realistic Civic & Public-Interest Test Repos
│   ├── civic-pension-calculator/   # Civic pension deduction engine
│   ├── disaster-supply-allocator/  # Emergency relief logistics allocator
│   └── water-quality-monitor/      # Real-time municipal water sensor telemetry
│
├── benchmark/                      # Deterministic Edge-Case Benchmark
│   ├── repo/                       # Civic audit & leap-year timestamp service
│   └── run_benchmark.py            # Standalone benchmark execution runner
│
├── tests/                          # Pipeline unit test suite
│   └── test_pipeline.py            # Verifies all 5 pipeline stages & algorithms
│
├── check_llm_connection.py         # LLM API connection & credentials validator
├── main.py                         # CLI entry point
├── .env.example                    # Environment variable template
├── PULL_REQUEST.md                 # Generated reviewer PR markdown artifact
└── README.md
```

---

## ⚡ Quickstart & Installation

### 1. Prerequisites & Virtual Environment

Python 3.10 or higher is required.

```bash
# Clone repository
git clone <repository-url>
cd "git error tracker"

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install fastapi uvicorn pytest hypothesis coverage httpx python-dotenv
# Optional: Install provider SDKs if using live models
pip install google-genai openai anthropic
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` to configure your preferred LLM provider and API keys:

```ini
# Primary LLM Provider: "gemini", "openai", "anthropic", or "mock"
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash

# API Keys
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# GitHub Token (Optional: for direct PR creation on GitHub)
GITHUB_TOKEN=ghp_...
```

### 3. Verify LLM Credentials & Connectivity

Run the diagnostic script to ensure API keys and network connectivity are operational:

```bash
python3 check_llm_connection.py
```

---

## 🖥️ Usage Modes

### Mode A: Interactive Web Dashboard (Recommended)

Start the FastAPI application:

```bash
uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser to `http://localhost:8000`. From the web dashboard:
1. Select one of the pre-configured civic repositories (or provide a custom repository path).
2. Choose your LLM provider (`gemini`, `openai`, `anthropic`, or `mock`).
3. Click **Start Repair** and observe the live SSE progress stream, Ochiai rankings, hypothesis exploration, and verification gates.
4. Review the generated unified diff, approve the patch, and publish a Pull Request directly to GitHub or a local git branch.

---

### Mode B: Command-Line Interface (CLI)

Run the autonomous repair pipeline directly against any repository:

```bash
# Run against a specific civic test repository using Gemini
python3 main.py --repo test_repositories/civic-pension-calculator --provider gemini --model gemini-2.5-flash

# Run against the disaster supply allocator
python3 main.py --repo test_repositories/disaster-supply-allocator --provider gemini

# Run with custom iteration ceiling and output file
python3 main.py --repo /path/to/target/repo --max-iterations 5 --output-pr PULL_REQUEST.md
```

CLI Arguments:
- `--repo`: Absolute or relative path to the target repository (default: `benchmark/repo`).
- `--provider`: LLM provider (`gemini`, `openai`, `anthropic`, `mock`).
- `--model`: Specific model name (e.g. `gemini-2.5-flash`, `gpt-4o`, `claude-3-5-sonnet-20241022`).
- `--max-iterations`: Maximum repair iterations ceiling (default: `5`).
- `--output-pr`: Filepath to write the generated markdown PR (default: `PULL_REQUEST.md`).
- `--no-property`: Disable Gate 2 Property-Based Testing.
- `--no-mutation`: Disable Gate 3 AST Mutation Testing.

---

### Mode C: Deterministic Edge-Case Benchmark (Offline)

To test the entire 5-stage pipeline deterministically without external API calls:

```bash
python3 benchmark/run_benchmark.py
```

This validates the complete loop:
1. Runs tests on `benchmark/repo` and captures failing leap-year timezone parsing.
2. Calculates Ochiai suspiciousness, isolating the failure to line 42 of `timestamp_parser.py`.
3. Synthesizes an algebraic patch that handles leap years properly.
4. Executes baseline unit regression, Hypothesis property tests, and AST mutation checks.
5. Produces the `PULL_REQUEST.md` artifact.

---

## 🧪 Pipeline Test Suite

Run the unit tests covering all 5 stages of the pipeline:

```bash
python3 -m pytest tests/test_pipeline.py -v
```

This verifies:
- Manifest detection for Python / Pytest projects.
- Ochiai formula correctness with known test pass/fail matrices.
- AST context extraction and enclosing block detection.
- Unified git diff parsing and application.
- AST mutation operator injection (arithmetic, comparison, boolean).
- Multi-layer verification matrix aggregation.
- Reviewer PR packaging and SDG alignment headers.

---

## 📋 Generated Pull Request Artifact (`PULL_REQUEST.md`)

When all three verification gates pass, the pipeline generates a comprehensive, reviewer-ready Markdown Pull Request containing:

1. **UN SDGs Alignment Header**: Identifies specific SDG targets (e.g., Target 9.1 resilient infrastructure, Target 16.6 transparent institutions).
2. **Competing Root-Cause Hypotheses**: Documents 3–5 hypotheses evaluated during synthesis.
3. **Mechanical Root Cause Analysis**: Precise technical description of the underlying fault.
4. **Line-by-Line Logic Summary**: Exact explanation of the modifications made.
5. **Unified Git Diff**: Standard `diff` block applicable directly via `git apply`.
6. **Multi-Layer Verification Matrix**:
   - Gate 1 (Regression): 100% baseline test pass rate.
   - Gate 2 (Property-Based): Number of invariant examples tested via Hypothesis without falsification.
   - Gate 3 (Mutation Score): Percentage of injected AST mutants detected and killed.
7. **Maintainer Deployment Checklist**: Pre-flight verification steps for repository owners.

---

## 📄 License & Ethical Use

Designed specifically for public-interest technologies, open civic infrastructure, and humanitarian digital public goods under the principles of **UN SDG 9** and **UN SDG 16**.
