# Workflow vs Agent — Fundamental Analysis of Brazilian Stocks

Experiment comparing **workflow** and **autonomous agent** approaches for fundamental analysis of Brazilian stocks using the OpenAI API.

> **Looking for the paper results?**
> - *"A Financial Agent for Fundamental Analysis: An Empirical Investigation in the Brazilian Stock Market"* (**ICLR 2026 Workshop on Advances in Financial AI**): [`paper/iclr-2026-workshop`](../../tree/paper/iclr-2026-workshop) branch.
> - *"Lightweight LLM Trading Agents for the Brazilian Stock Market with Fundamental Analysis and Material Disclosure Summarization"* (**ICAIF 2026**): [`paper/icaif-2026`](../../tree/paper/icaif-2026) branch, with a step-by-step reproduction tutorial.

## Project structure

```
./
├── main.py                                # Experiment: fundamental analysis (agent vs workflow)
├── main_workflow.py                       # Experiment: investment house (analysts + manager)
├── run_experiments.py                     # Runs the 4 investment-house variations (with/without material facts, GPT-5-mini/Sabiazinho-4)
├── run_experiment_fundamentalista_llm.py  # LLM fundamental analyst + material facts: reruns only the manager on existing outputs
├── manager_evaluation.ipynb               # Trading return / Sharpe evaluation of the investment-house experiments
├── manager_evaluation_v2.ipynb            # Same, with target-price-triggered sells
├── evaluation_final.ipynb                 # Evaluation of the agent vs workflow experiment
├── dev.env                                # Environment variables (copy to .env)
├── pyproject.toml / uv.lock / .python-version
├── data/                                  # Zipped databases and material-facts caches (see below)
├── results/                               # baseline (price only), manager (LLM analyst), fundamental_analysis
├── results_v2/                            # Outputs of run_experiments.py
└── src/
    ├── settings.py                 # Centralizes paths read from environment variables
    ├── db/                         # SQL queries (CVM DFP/ITR and prices)
    ├── tools/                      # OpenAI Agents tools (function tools)
    ├── financial_agents/           # Agent definitions (analyst, manager)
    └── experiments/
        ├── fundamental_analysis/   # Agent vs workflow experiment (main.py)
        │   ├── agent.py
        │   ├── workflow.py
        │   └── config.py           # Stock list (STOCKS)
        └── manager/                # Investment house experiment (main_workflow.py)
            ├── fundamental_analyst.py  # Rule-based fundamental analyst (no LLM)
            ├── material_facts_report.py
            ├── manager.py
            └── config.py
```

## Setup

### 1. Install dependencies

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/). uv installs the Python version pinned in `.python-version` (3.13).

```bash
uv sync
```

### 2. Prepare the data

The databases and caches are versioned as `.zip` files in `data/`:

| File in `data/` | Content |
|---|---|
| `cvm.db.zip` → `cvm.db` | SQLite with CVM DFP/ITR statements (`DFP_ITR_CVM`) and share counts (`CVM_SHARE_COMPOSITION`) |
| `prices.db.zip` → `prices.db` | SQLite with B3 daily quotes (`COTAHIST`) |
| `raw_facts_cache.json.zip` → `raw_facts_cache.json` | Pre-fetched material facts (*Fatos Relevantes*, CVM IPE) as text, keyed `TICKER\|YEAR\|MONTH`, for the stocks in `src/experiments/manager/config.py` from 2023-07 to 2025-11. With it present, `run_experiments.py` downloads nothing from CVM |
| `material_facts.zip` → `material_facts/` | Material-fact PDFs converted to Markdown (fallback cache) |
| `gold.csv` | Reference indicator values for the agent vs workflow experiment |
| `terms.csv` | Definitions of the accounting terms |

Extract them from the repository root:

```bash
cd data
for f in cvm.db.zip prices.db.zip raw_facts_cache.json.zip material_facts.zip; do
  unzip -o "$f" -x '__MACOSX/*' '*.DS_Store'
done
cd ..
```

(`caution: excluded filename not matched` messages are harmless.) The extracted files are git-ignored. Missing material facts are downloaded on demand into `data/ipe_cache/`.

### 3. Configure environment variables

Copy `dev.env` to `.env` and update the values:

```bash
cp dev.env .env
```

Required variables in `.env`:

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key |
| `MARITACA_API_KEY` | Maritaca AI API key (only for Sabiazinho-4 runs) |
| `DB_PATH` | Path to `cvm.db` |
| `PRICE_DB_PATH` | Path to `prices.db` |
| `PRICE_FILE` | Path to the reference prices CSV |
| `WRITE_FOLDER` | Output folder for results (default: `results`) |

## Running the experiments

### Experiment: fundamental analysis (agent vs workflow)

Compares the agent and workflow approaches on the task of computing fundamental indicators for a list of stocks.

```bash
uv run main.py
```

Results are saved to `results/<model>/agent_<reflection>/` and `results/<model>/workflow_<reflection>/`.

### Experiment: investment house

Simulates an investment house with two sequential agents: a fundamental analyst and a portfolio manager, iterating monthly over 2024–2025.

```bash
uv run main_workflow.py
```

Results are saved to `results/<stock_id>/`.

### Experiment: investment house variations

Runs the 4 variations (rule-based fundamental analyst without material facts; with material facts via GPT-5-mini; via Sabiazinho-4; and a hybrid with Sabiazinho-4 facts and a GPT-5-mini manager):

```bash
uv run run_experiments.py                                  # writes to results_v2/<variation>/
uv run run_experiments.py --output-root my_run --only completo_gpt5mini
```

Runs are resumable: stock/months already present in the output folder are skipped, so use a new `--output-root` to start from scratch.

To combine the LLM fundamental analyst (`results/manager`) with the GPT-5-mini material-facts reports (`results_v2/completo_gpt5mini`) and rerun only the manager:

```bash
uv run run_experiment_fundamentalista_llm.py              # writes to results_v2/completo_analista_llm_gpt5mini/
```

### Evaluation

```bash
uv run --with jupyterlab jupyter lab manager_evaluation.ipynb   # investment-house strategies
uv run --with jupyterlab jupyter lab evaluation_final.ipynb     # agent vs workflow
```

`manager_evaluation.ipynb` reads `results/` and `results_v2/` (change `RESULTS_V2_ROOT` to evaluate another output root); strategies whose folder is missing are reported as empty.
