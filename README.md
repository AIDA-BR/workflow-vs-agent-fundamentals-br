# Lightweight LLM Trading Agents for the Brazilian Stock Market

This branch contains the code, data and outputs needed to reproduce the experiments reported in the paper:

> **"Lightweight LLM Trading Agents for the Brazilian Stock Market with Fundamental Analysis and Material Disclosure Summarization"**
> ICAIF 2026 — *(publication details and BibTeX to be added upon acceptance)*

The paper proposes a cost-efficient multi-agent framework for monthly single-stock decisions (buy / hold / sell) on 9 Brazilian stocks, from January 2024 to December 2025. A GPT-5-mini (or Sabiazinho-4) **financial manager** decides based on the output of three analysts:

| Analyst | Type | Code |
|---|---|---|
| Price Analyst | Rule-based (SQL over B3 daily quotes) | [src/db/](src/db/), [src/tools/bovespa_price.py](src/tools/bovespa_price.py) |
| Fundamental Analyst | **Rule-based**: computes 32 indicators from official CVM DFP/ITR filings, no LLM | [src/experiments/manager/fundamental_analyst.py](src/experiments/manager/fundamental_analyst.py), [src/financial_agents/financial_analyst.py](src/financial_agents/financial_analyst.py) |
| Material Disclosure Analyst | LLM, two stages: monthly summaries → six-month report | [src/experiments/manager/material_facts_report.py](src/experiments/manager/material_facts_report.py), [src/financial_agents/material_facts_summarizer.py](src/financial_agents/material_facts_summarizer.py) |
| Financial Manager | LLM (reasoning effort `high`, verbosity `medium`) | [src/experiments/manager/manager.py](src/experiments/manager/manager.py), [src/financial_agents/financial_manager.py](src/financial_agents/financial_manager.py) |

The *Fund.LLM* baseline (LLM-based fundamental analyst) comes from our previous paper, *"A Financial Agent for Fundamental Analysis: An Empirical Investigation in the Brazilian Stock Market"* (ICLR 2026 Workshop on Advances in Financial AI). Its code is on the [`paper/iclr-2026-workshop`](../../tree/paper/iclr-2026-workshop) branch; its outputs are included here in `results/manager/`.

---

## Quick start: reproduce Table 1

You do **not** need API keys to reproduce the paper's numbers: all model outputs are versioned in `results/`.

```bash
git clone -b paper/icaif-2026 https://github.com/AIDA-BR/workflow-vs-agent-fundamentals-br.git
cd workflow-vs-agent-fundamentals-br
uv sync
uv run --with jupyterlab jupyter lab manager_evaluation.ipynb   # Run All
```

The notebook prints the per-stock trading returns and the aggregate table. The values in the **Norm. Return** column correspond to the paper's *trading return*, and **Sharpe** corresponds to the annualized Sharpe Ratio (SELIC = 15%).

To run it headless instead:

```bash
uv run --with nbconvert --with ipykernel jupyter nbconvert --to notebook --execute \
  manager_evaluation.ipynb --output manager_evaluation.executed.ipynb
```

Rerunning the experiments themselves (which calls the LLM APIs) is described in [Rerunning the experiments](#rerunning-the-experiments).

---

## Project structure

```
./
├── run_experiments.py                     # Runs the 4 configurations of this paper (Fund.Rule, +FactsGPT, +FactsSabiá, Hybrid)
├── run_experiment_fundamentalista_llm.py  # Additional experiment: Fund.LLM + material facts (GPT-5-mini)
├── main_workflow.py                       # Investment-house pipeline (analysts + manager), used by the scripts above
├── main.py                                # Agent vs workflow experiment (ICLR 2026 workshop paper)
├── manager_evaluation.ipynb               # Evaluation notebook → Table 1
├── evaluation_final.ipynb                 # Evaluation notebook of the ICLR 2026 workshop paper
├── dev.env                                # Environment variable template (copy to .env)
├── pyproject.toml / uv.lock
├── data/                                  # Databases and material-disclosure caches (zipped, see below)
├── results/                               # All experiment outputs (see "Results")
└── src/
    ├── settings.py                        # Paths read from environment variables
    ├── db/                                # SQL helpers (CVM DFP/ITR and prices)
    ├── tools/                             # Agent tools, incl. material_facts.py (CVM disclosure fetching)
    ├── financial_agents/                  # Agent definitions (analyst, manager, disclosure summarizer)
    └── experiments/
        ├── providers.py                   # OpenAI / Maritaca (Sabiazinho) client selection
        ├── fundamental_analysis/          # Agent vs workflow experiment (ICLR paper)
        └── manager/                       # Investment-house experiment (this paper)
            ├── config.py                  # The 9 stocks (ticker, name, CNPJ)
            ├── fundamental_analyst.py     # Rule-based fundamental analyst
            ├── material_facts_report.py   # Material Disclosure Analyst (monthly + six-month summaries)
            └── manager.py                 # Financial manager
```

---

## Data

All inputs are public data from the Brazilian securities commission (CVM) and B3. Large files are versioned as `.zip` archives in `data/`:

| File in `data/` | Content | Source | Used by |
|---|---|---|---|
| `cvm.db.zip` → `cvm.db` | SQLite with tables `DFP_ITR_CVM` (annual DFP and quarterly ITR statements) and `CVM_SHARE_COMPOSITION` (number of shares) | [CVM open data](https://dados.cvm.gov.br/dataset/) — [DFP](https://dados.cvm.gov.br/dataset/cia_aberta-doc-dfp), [ITR](https://dados.cvm.gov.br/dataset/cia_aberta-doc-itr) | Fundamental Analyst (`DB_PATH`) |
| `prices.db.zip` → `prices.db` | SQLite with table `COTAHIST` (B3 daily quotes) | B3 COTAHIST / [finbr](https://github.com/renanmoretto/finbr) | Price Analyst and decision-day prices (`PRICE_DB_PATH`) |
| `raw_facts_cache.json.zip` → `raw_facts_cache.json` | Raw material disclosures (*Fatos Relevantes*) already converted to text, keyed `TICKER\|YEAR\|MONTH`, for all 9 stocks from 2023-07 to 2025-11 (the six-month windows of every decision) | [CVM IPE dataset](https://dados.cvm.gov.br/dataset/cia_aberta-doc-ipe), documents labeled *Fato Relevante* | Material Disclosure Analyst (`run_experiments.py` pre-fetch step) |
| `material_facts.zip` → `material_facts/<TICKER>/*.md` | Disclosure PDFs converted to Markdown with docling | Same as above | Only as a fallback cache when an entry is missing from `raw_facts_cache.json` |
| `gold.csv` | Reference indicator values for the agent vs workflow experiment | — | ICLR paper only (`PRICE_FILE`, must exist for `src/settings.py`) |
| `terms.csv` | Definitions of the accounting terms (Portuguese) | — | Reference only |

`raw_facts_cache.json` is complete for every stock and month used in the paper, so **no download from CVM happens** when it is present. If an entry is missing, `src/tools/material_facts.py` downloads the yearly IPE archive into `data/ipe_cache/` (created on demand, git-ignored) and converts the PDFs with docling.

### Unzipping the data

Only needed to [rerun the experiments](#rerunning-the-experiments) (the evaluation notebook reads `results/` only). From the repository root:

```bash
cd data
for f in cvm.db.zip prices.db.zip raw_facts_cache.json.zip material_facts.zip; do
  unzip -o "$f" -x '__MACOSX/*' '*.DS_Store'
done
cd ..
```

(`caution: excluded filename not matched` messages are harmless.)

Expected result:

```
data/
├── cvm.db
├── prices.db
├── raw_facts_cache.json
├── material_facts/{ALUP,AURE,CPLE,EALT,ENEV,EQTL,PETR,RECV,VALE}/*.md
├── gold.csv
└── terms.csv
```

The extracted files are git-ignored.

---

## Rerunning the experiments

### 1. Install dependencies

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/). uv installs the Python version pinned in `.python-version` (3.13) automatically.

```bash
uv sync
```

### 2. Unzip the data

See [Unzipping the data](#unzipping-the-data).

### 3. Configure environment variables

```bash
cp dev.env .env
```

Then edit `.env`:

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key (GPT-5-mini) |
| `MARITACA_API_KEY` | Maritaca AI API key (Sabiazinho-4) — only needed for `completo_sabiazinho4` and `hibrido_fatos_sabiazinho4_gestor_gpt5mini` |
| `DB_PATH` | Path to `cvm.db` (default `data/cvm.db`) |
| `PRICE_DB_PATH` | Path to `prices.db` (default `data/prices.db`) |
| `PRICE_FILE` | Path to `gold.csv` (default `data/gold.csv`) |

The remaining variables of `dev.env` (`MCP_*`, `JWT_MCP_URL`, `WRITE_FOLDER`) are not used by this paper's scripts and can keep their template values.

### 4. Run this paper's configurations

> **Important:** the scripts are *resumable* — any stock/month whose output already exists in the target folder is skipped. Running them against the default `results/` folder therefore does nothing. Always write to a fresh folder with `--output-root`.

```bash
uv run run_experiments.py --output-root reproduced
```

This first loads the material disclosures from `data/raw_facts_cache.json`, then runs, sequentially, for each of the 9 stocks and each month of 2024–2025:

| Folder in `reproduced/` | Paper column | Fundamental Analyst | Material Disclosure Analyst | Manager |
|---|---|---|---|---|
| `sem_fato_relevante_gpt5mini` | Fund.Rule | Rule-based | — | GPT-5-mini |
| `completo_gpt5mini` | +FactsGPT | Rule-based | GPT-5-mini | GPT-5-mini |
| `completo_sabiazinho4` | +FactsSabiá | Rule-based | Sabiazinho-4 | Sabiazinho-4 |
| `hibrido_fatos_sabiazinho4_gestor_gpt5mini` | Hybrid | Rule-based | Sabiazinho-4 | GPT-5-mini |

To run only some configurations (e.g. without a Maritaca key):

```bash
uv run run_experiments.py --output-root reproduced --only sem_fato_relevante_gpt5mini completo_gpt5mini
```

If a run is interrupted (or an API error happens; the scripts retry after 1 minute), simply launch the same command again and it continues where it stopped.

### 5. (Optional) Additional experiment: Fund.LLM + material facts

Combines the LLM-based fundamental analyst of the ICLR paper (`results/manager/`) with the GPT-5-mini material disclosure reports of `completo_gpt5mini`, and reruns only the GPT-5-mini manager. This experiment is **not part of the submitted Table 1**; it was run to answer a reviewer's question.

```bash
# using the published disclosure reports in results/completo_gpt5mini
uv run run_experiment_fundamentalista_llm.py --output-root reproduced
# or using the ones you generated in step 4
uv run run_experiment_fundamentalista_llm.py --input-root reproduced --output-root reproduced
```

### 6. Evaluate your run

Open `manager_evaluation.ipynb`, set `RESULTS_ROOT = "reproduced"` in the first code cell and run all cells. The Price and Fund.LLM baselines are always read from `results/baseline` and `results/manager`.

Note that LLM outputs are not deterministic, so a rerun will produce numbers close to, but not identical to, those in the paper. The exact outputs behind the paper are the ones in `results/`.

---

## Results

All outputs are in `results/`. The values below are the ones printed by `manager_evaluation.ipynb` (trading return = Σ(sell − avg_buy) / Σ avg_buy over all trades; annualized Sharpe with SELIC = 15%).

| Folder | Paper column | Description | Trading return | Sharpe |
|---|---|---|---|---|
| — | B&H | Buy on the first month, hold until the last (computed in the notebook) | −1.35% | 0.2124 |
| `results/baseline` | Price | Manager sees only price information | 18.04% | 1.7188 |
| `results/manager` | Fund.LLM | LLM-based fundamental analyst + manager (Ferreira et al., 2026) | 9.50% | 0.5215 |
| `results/sem_fato_relevante_gpt5mini` | Fund.Rule | Rule-based fundamental analyst + GPT-5-mini manager | 6.74% | 0.1875 |
| `results/completo_gpt5mini` | +FactsGPT | Fund.Rule + GPT-5-mini material disclosure analyst | **14.44%** | 1.0265 |
| `results/completo_sabiazinho4` | +FactsSabiá | Fund.Rule + Sabiazinho-4 for disclosures and manager | −1.56% | 0.0011 |
| `results/hibrido_fatos_sabiazinho4_gestor_gpt5mini` | Hybrid | Sabiazinho-4 for disclosures, GPT-5-mini manager | 9.78% | 0.7264 |
| `results/completo_analista_llm_gpt5mini` | *(additional, not in Table 1)* | Fund.LLM + GPT-5-mini disclosures + GPT-5-mini manager | 5.17% | 0.1014 |
| `results/fundamental_analysis` | — | Agent vs workflow outputs of the ICLR 2026 workshop paper | — | — |

Per-stock returns are printed in the notebook and match Table 1 of the paper.

### Layout of each results folder

```
results/<configuration>/
├── results_sample.json            # One record per stock × month: ticker, date, prices, fundamental indicators,
│                                  #   previous decision — i.e. the table the manager receives
├── decisions_sample.json          # One record per stock × month: stock_id, analysis_date, recommendation,
│                                  #   target_price, justification
├── monthly_summary_cache.json     # Monthly disclosure summaries keyed "TICKER|YEAR|MONTH" (configurations from run_experiments.py)
└── <TICKER>/
    ├── <YYYY-MM-DD>_analyst_0.json         # Fundamental analyst output (absent in baseline/, which has no analyst)
    ├── <YYYY-MM-DD>_material_facts_0.txt   # Six-month material disclosure report given to the manager (configurations with facts)
    └── <YYYY-MM-DD>_manager_0.json         # Raw manager run (decision, justification, target price, token usage)
```

Decision dates are the first business day of each month (B3 calendar), from 2024-01-02 to 2025-12-01. The evaluation only needs `results_sample.json` (prices) and `decisions_sample.json` (recommendations); the per-stock files are kept for inspection of the agents' reasoning.
