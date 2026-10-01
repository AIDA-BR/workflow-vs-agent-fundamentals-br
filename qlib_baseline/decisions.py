"""Turn model scores (predicted 1-month returns) into the paper's monthly decisions.

Two rules, applied independently on each decision date to the 9 stocks:

* ``threshold``: Comprar if score > +tau, Vender if score < -tau, otherwise Manter.
* ``rank``: Comprar the TOP_K best-scored stocks, Vender the TOP_K worst, Manter the rest.

The output folder has the same files as the LLM experiments (``decisions_sample.json`` and
``results_sample.json``), so it can also be evaluated by ``manager_evaluation.ipynb``.
"""

import json
from pathlib import Path

import pandas as pd

from config import REFERENCE_FOLDER, RESULTS_DIR, STOCKS, THRESHOLD, TOP_K


def apply_rule(preds: pd.DataFrame, rule: str, tau: float = THRESHOLD, k: int = TOP_K) -> pd.Series:
    if rule == "threshold":
        rec = pd.Series("Manter", index=preds.index)
        rec[preds.score > tau] = "Comprar"
        rec[preds.score < -tau] = "Vender"
        return rec
    if rule == "rank":
        rank = preds.groupby("analysis_date").score.rank(ascending=False, method="first")
        n = preds.groupby("analysis_date").score.transform("size")
        rec = pd.Series("Manter", index=preds.index)
        rec[rank <= k] = "Comprar"
        rec[rank > n - k] = "Vender"
        return rec
    raise ValueError(f"unknown rule {rule!r}")


def make_decisions(preds: pd.DataFrame, rule: str, **kwargs) -> list[dict]:
    """Decisions grouped by stock (paper order) and chronological, as the evaluation expects."""
    preds = preds.assign(recommendation=apply_rule(preds, rule, **kwargs))
    preds = preds.assign(order=preds.stock_id.map(STOCKS.index)).sort_values(
        ["order", "analysis_date"]
    )
    return [
        {
            "recommendation": r.recommendation,
            "justification": f"qlib LightGBM score={r.score:.4f} (rule={rule})",
            "target_price": None,
            "analysis_date": r.analysis_date,
            "stock_id": r.stock_id,
            "score": r.score,
        }
        for r in preds.itertuples()
    ]


def reference_prices() -> list[dict]:
    """COTAHIST price records of the paper (same close prices as every LLM strategy)."""
    with open(REFERENCE_FOLDER / "results_sample.json") as f:
        records = json.load(f)
    keep = ["ACAO", "DATA_DO_PREGAO", "PRECO_ULTIMO_NEGOCIO"]
    return [{k: r[k] for k in keep} for r in records]


def write_strategy(
    preds: pd.DataFrame, rule: str, name: str, results_dir: Path = RESULTS_DIR, **kwargs
) -> Path:
    """Write results/<name>/{decisions_sample,results_sample}.json + predictions.csv."""
    folder = results_dir / name
    folder.mkdir(parents=True, exist_ok=True)
    decisions = make_decisions(preds, rule, **kwargs)
    prices = {(r["ACAO"], r["DATA_DO_PREGAO"]): r for r in reference_prices()}
    results = [prices[(d["stock_id"], d["analysis_date"])] for d in decisions]
    with open(folder / "decisions_sample.json", "w") as f:
        json.dump(decisions, f, ensure_ascii=False, indent=2)
    with open(folder / "results_sample.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    preds.to_csv(folder / "predictions.csv", index=False)
    return folder
