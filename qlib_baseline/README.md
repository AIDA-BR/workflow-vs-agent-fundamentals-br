# qlib baseline: can traditional quant models match the LLM agents?

The LLM agents of the ICAIF 2026 paper (see the [main README](../README.md)) trade 9 B3 stocks
monthly from January 2024 to December 2025. Every decision costs several LLM calls. This
sub-project asks whether a **traditional quantitative pipeline** gets a similar *trading return* on
the **same stocks, dates and evaluation**. The pipeline is [Microsoft qlib](https://github.com/microsoft/qlib)
factors plus a LightGBM regressor, and it costs a few minutes of CPU.

```
qlib_baseline/
├── config.py         stocks, decision dates, label, LightGBM params, FEATURE SETS  ← edit here
├── handler.py        Alpha158Plus: qlib's Alpha158 factors + any extra fields
├── walk_forward.py   monthly retraining with D-1 data → output/predictions_<features>_<universe>.csv
├── decisions.py      predicted return → Comprar / Vender / Manter → results/qlib_*/
├── evaluation.py     the paper's evaluation functions, copied verbatim from manager_evaluation.ipynb
├── csv_to_qlib.py    add your own features from a CSV (e.g. environmental factors)
├── export_bundle.py  (maintainers) rebuild data/qlib_data.zip from the fin-difusion bundle
├── qlib_io.py        reader/writer of qlib's .day.bin format
└── output/           cached predictions (committed, so the notebook runs without retraining)
../qlib_evaluation.ipynb   runs everything and compares against the paper (Table 1)
../data/qlib_data.zip      the qlib dataset (2017-01 → 2026-01, 176 B3 tickers)
```

## 1. Setup

qlib 0.9.7 only ships wheels up to Python 3.12, while the rest of the repo uses 3.13. So this
folder has its own environment.

```bash
# from the repository root
unzip -o data/qlib_data.zip -d data           # → data/qlib_data/{calendars,instruments,features}
cd qlib_baseline
uv sync                                       # Python 3.12 + pyqlib, lightgbm, jupyter
cd ..
qlib_baseline/.venv/bin/jupyter lab qlib_evaluation.ipynb
```

To run the notebook headless instead:

```bash
qlib_baseline/.venv/bin/jupyter nbconvert --to notebook --execute qlib_evaluation.ipynb \
    --output qlib_evaluation.executed.ipynb
```

The notebook reuses the committed predictions in `output/` by default. Set `RETRAIN = True` in its
first cell to retrain everything; on a laptop that takes a few minutes. You can also train from the
command line:

```bash
cd qlib_baseline
uv run walk_forward.py                                    # 2 feature sets × 2 universes × 24 months
uv run walk_forward.py --features fundamentals --universe paper9 --output-dir output_test
```

`walk_forward.py` skips any model whose `output/predictions_*.csv` already exists. Delete the file,
or use a new `--output-dir`, to retrain.

## 2. How the model works

### Data (`data/qlib_data`)
The data is a subset of the fin-difusion qlib bundle for B3:
- **Prices:** daily OHLCV, adjusted for splits and dividends.
- **Fundamentals:** taken from the CVM DFP/ITR filings. Each value is visible only from its
  **publication date** and is forward-filled until the next filing, so there is no look-ahead.
  Fundamentals start on 2021-03-31 and are NaN before then. LightGBM handles NaN natively.
- **Universes** (`instruments/`):
  - `broad`: the point-in-time B3 liquidity universe (top-100 stocks by traded value, re-ranked
    every 4 months, 176 tickers over the period) plus the 9 paper stocks for the whole period.
  - `paper9`: only the 9 stocks.

### Features (`config.FEATURE_SETS`)
| Feature set | Columns |
|---|---|
| `price` | **Alpha158**, qlib's standard price/volume factor library: K-bar shape, normalised OHLC, and rolling 5/10/20/30/60-day momentum, volatility, moving averages, max/min, quantiles, rank, correlation of price and volume, etc. The bundle has no VWAP, so 157 factors are used. |
| `fundamentals` | Alpha158 + 19 fundamentals mirroring the paper's rule-based analyst (`src/financial_agents/financial_analyst.py`) — see the table below |

| qlib field | Paper indicator | qlib field | Paper indicator |
|---|---|---|---|
| `$pe` | P/L | `$gross_margin` | Marg. Bruta |
| `$pb` | P/VP | `$ebit_margin` | Marg. EBIT |
| `$p_ebit` | P/EBIT | `$net_margin` | Marg. Líquida |
| `$ps` | PSR | `$ebit_assets` | EBIT/Ativo |
| `$p_assets` | P/Ativos | `$roic` | ROIC |
| `$p_wc` | P/Cap. Giro | `$roe` | ROE |
| `$p_nla` | P/Ativ Circ Liq | `$current_ratio` | Liquidez Corr |
| `$ev_ebitda` | EV/EBITDA | `$debt_to_equity` | Div Br/Patrim |
| `$ev_ebit` | EV/EBIT | `$asset_turnover` | Giro Ativos |
| `Log($mktcap+1)` | market value (size) | | |

### Label
The label is `Ref($close, -22) / Ref($close, -1) - 1`. On feature date *t* = D-1 this is the return
from the close of the decision day D to the close ~21 trading days later. That is the holding period
of a monthly decision in the paper.

### Monthly walk-forward with D-1 data (`walk_forward.py`)
For each of the paper's 24 decision dates D (the first business day of the month):

1. **Purged training window:** feature dates from 2018-01-01 up to the last day whose label is
   already known on D-1 (D-1 minus 22 trading days). No future return enters training.
2. **Early stopping:** the last 6 months of that window are the validation set.
3. **Model:** LightGBM regression (MSE) with the same hyper-parameters as fin-difusion. It is
   **retrained from scratch every month**.
4. **Inference:** the 9 stocks are scored with their **D-1 features**. The score is the predicted
   1-month return.

Features are not normalised: trees are scale-invariant, and normalising would need statistics
fitted on a time range. The label stays raw, so the score reads as an expected return.

### From scores to decisions (`decisions.py`)
| Rule | Comprar | Vender | Manter |
|---|---|---|---|
| `threshold` (τ = `config.THRESHOLD`, default 0) | score > τ | score < −τ | otherwise |
| `rank` (k = `config.TOP_K`, default 3) | top-k of the 9 | bottom-k of the 9 | the rest |

The notebook also reports a sensitivity table for τ.

### Evaluation (`evaluation.py`)
The functions are identical to `manager_evaluation.ipynb`:
- A *Comprar* adds one share at the COTAHIST close of D.
- A *Vender* closes the position against the average buy price.
- Positions still open at the end are closed at the last decision price.
- **Norm. Return** = Σ(sell − avg buy) / Σ avg buy. This is the paper's *trading return*, the main
  comparison metric.
- **Sharpe** is annualised with SELIC = 15%.

The notebook checks that the paper's rows reproduce Table 1 exactly. The strategy folders
`results/qlib_*` have the same files as the LLM experiments, so they can also be evaluated by
`manager_evaluation.ipynb`.

## 3. Adding new features (e.g. environmental factors)

**Step 1 — put the data in a CSV**, one row per (date, ticker) and one column per feature:

```csv
date,ticker,env_score,co2_intensity
2023-03-31,PETR4,61.2,0.84
2023-03-31,VALE3,55.0,1.12
2023-06-30,PETR4,62.0,0.80
```

- `date` must be when the value became **public** (for example, the release date of the
  sustainability report), not the period it refers to. If you only have reference dates, pass
  `--lag-days` (see Step 2) so the model does not see the future.
- Tickers are B3 codes (`PETR4`). Only tickers already in the bundle are converted.
- Column names: lower-case letters, digits and `_`. Each one becomes a qlib field `$<column>`.
- Frequency can be anything (daily, quarterly, yearly). Values are forward-filled to the next
  observation.
- `data/custom_features_example.csv` is a **synthetic** example with two random columns,
  `env_score_example` and `co2_intensity_example`, for the 9 stocks. Use it to test the workflow.
  It carries no information.

**Step 2 — convert it into the qlib dataset**

```bash
cd qlib_baseline
uv run csv_to_qlib.py ../data/custom_features_example.csv
# optional: --columns env_score  --lag-days 90  --ffill-limit 252  --qlib-dir <other dataset>
```

This writes `data/qlib_data/features/<ticker>/<column>.day.bin` and prints the line to paste into
`config.py`. Check the result in Python:

```python
import qlib; from qlib.data import D
qlib.init(provider_uri="../data/qlib_data")
D.features(["PETR4"], ["$env_score_example"], "2023-01-01", "2023-12-31")
```

**Step 3 — add the feature to a model** in `config.py`:

```python
# Option A: add it to both existing models
EXTRA_FEATURES = [("$env_score_example", "ENV_SCORE"), ("$co2_intensity_example", "CO2_INTENSITY")]

# Option B (recommended for a comparison): a new model next to the existing ones
ENV_FEATURES = [("$env_score_example", "ENV_SCORE"), ("$co2_intensity_example", "CO2_INTENSITY")]
FEATURE_SETS = {
    "price": [],
    "fundamentals": FUNDAMENTAL_FEATURES,
    "price_env": ENV_FEATURES,
    "fundamentals_env": FUNDAMENTAL_FEATURES + ENV_FEATURES,
}
```

Any qlib expression works, not just raw fields. For example, `"$co2_intensity_example / $ps"`,
`"Mean($env_score_example, 252)"`, or a change over the last year:
`"$env_score_example - Ref($env_score_example, 252)"`.

**Step 4 — rerun.** Run the notebook with `RETRAIN = False`. Existing models load from the cache and
only new feature sets are trained. If you change a set that already has cached predictions, delete
its `output/predictions_<set>_*.csv` first. New strategies show up as `results/qlib_<set>_*` in the
comparison tables.

**Coverage.** If the new data only covers the 9 stocks, the `broad` universe will have NaN for the
other tickers. LightGBM accepts that, but the `paper9` universe gives the cleaner test.

## 4. Rebuilding the dataset (maintainers)

`data/qlib_data.zip` was produced from the fin-difusion bundle (`b3_latest`, built 2026-08-30) with:

```bash
cd qlib_baseline
uv run export_bundle.py --source ~/Documents/workspace/fin-difusion/scripts/qlib/work/extracted/qlib_data
```

To add more bundle fields, such as macro `$m_selic` or `$div_yield`, extend `FUNDAMENTAL_FIELDS`
(or add a list) in `export_bundle.py` and re-export.
