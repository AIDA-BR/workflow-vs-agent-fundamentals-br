# Workflow vs Agent — Fundamental Analysis of Brazilian Stocks

Experiment comparing **workflow** and **autonomous agent** approaches for fundamental analysis of Brazilian stocks using the OpenAI API.

> **Looking for the paper results?** The code used to reproduce the experiments reported in the paper *"A Financial Agent for Fundamental Analysis: An Empirical Investigation in the Brazilian Stock Market"*, accepted at the **ICLR 2026 Workshop on Advances in Financial AI**, is available on the [`paper/iclr-2026-workshop`](../../tree/paper/iclr-2026-workshop) branch.

## Project structure

```
./
├── main.py                         # Experiment: fundamental analysis (agent vs workflow)
├── main_workflow.py                # Experiment: investment house (analyst + manager)
├── dev.env                         # Environment variables (copy to .env)
├── pyproject.toml
├── scripts/
│   ├── evaluation_final.ipynb      # Notebook with the reported results
│   ├── extract_fundamental_analysis.py
│   ├── parse_cvm.ipynb
│   └── parse_prices.ipynb
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
            ├── fundamental_analyst.py
            ├── manager.py
            └── config.py
```

## Setup

### 1. Install dependencies

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
uv sync
```

### 2. Prepare the databases

Extract the databases into the `data/` folder:

```
data/
├── cvm.db          # CVM DFP/ITR forms
├── prices.db       # Price history (COTAHIST)
└── gold.csv        # Reference prices for the experiments
```

### 3. Configure environment variables

Copy `dev.env` to `.env` and update the values:

```bash
cp dev.env .env
```

Required variables in `.env`:

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key |
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

### Evaluation

Open the notebook with the results reported in the paper:

```bash
uv run jupyter lab scripts/evaluation_final.ipynb
```
