"""Monthly walk-forward training and inference with D-1 data.

For every decision date D of the paper (first business day of the month):

* the model is **retrained** on samples whose label is already known on D-1, i.e. feature dates
  t with t + HORIZON + 1 trading days <= D-1 (purged so no future return leaks into training);
  the last VALID_MONTHS of that window are used for early stopping;
* the 9 paper stocks are **scored with the features of D-1** (the previous trading day);
* the score is the predicted return from the close of D to ~1 month later.

Usage:
    uv run walk_forward.py                                  # all feature sets x universes
    uv run walk_forward.py --features price --universe paper9 --dates 2024-01-02 2024-02-01
"""

import argparse
import logging
import os
from pathlib import Path

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import pandas as pd  # noqa: E402

from config import (  # noqa: E402
    FEATURE_SETS,
    EXTRA_FEATURES,
    HORIZON,
    LGB_PARAMS,
    QLIB_DIR,
    STOCKS,
    TRAIN_START,
    UNIVERSES,
    VALID_MONTHS,
    decision_dates,
)

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
logger = logging.getLogger("walk_forward")


def init_qlib(qlib_dir: Path = QLIB_DIR) -> None:
    import qlib
    from qlib.constant import REG_CN

    if not (qlib_dir / "calendars" / "day.txt").exists():
        raise SystemExit(f"{qlib_dir} not found — unzip data/qlib_data.zip first (see README)")
    # REG_CN only selects trading conventions; the calendar comes from the B3 bundle.
    qlib.init(provider_uri=str(qlib_dir), region=REG_CN, logging_level=logging.WARNING)


def fold_segments(calendar: pd.DatetimeIndex, decision_date: str) -> dict:
    """train / valid / test segments for one decision date (see module docstring)."""
    d = pd.Timestamp(decision_date)
    d_minus_1 = calendar[calendar < d][-1]
    pos = calendar.get_loc(d_minus_1)
    last_labelled = calendar[pos - (HORIZON + 1)]
    valid_start = calendar[calendar > last_labelled - pd.DateOffset(months=VALID_MONTHS)][0]
    train_end = calendar[calendar < valid_start][-1]
    return {
        "train": (pd.Timestamp(TRAIN_START), train_end),
        "valid": (valid_start, last_labelled),
        "test": (d_minus_1, d_minus_1),
    }


def run_model(
    features: str, universe: str, dates: list[str], extra_fields=None, end_time: str = "2026-01-30"
) -> pd.DataFrame:
    """Train one model per decision date; returns one row per (date, stock)."""
    from qlib.contrib.model.gbdt import LGBModel
    from qlib.data import D
    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandlerLP

    from handler import build_handler

    fields = FEATURE_SETS[features] + EXTRA_FEATURES if extra_fields is None else extra_fields
    logger.warning("Loading %s features for universe %s ...", features, universe)
    handler = build_handler(universe, fields, TRAIN_START, end_time)
    calendar = pd.DatetimeIndex(D.calendar(start_time=TRAIN_START, end_time=end_time))

    rows = []
    for date in dates:
        seg = fold_segments(calendar, date)
        dataset = DatasetH(handler=handler, segments=seg)
        model = LGBModel(**LGB_PARAMS)
        model.fit(dataset, verbose_eval=0)
        score = model.predict(dataset, segment="test")
        label = dataset.prepare("test", col_set="label", data_key=DataHandlerLP.DK_R)["LABEL0"]
        frame = pd.DataFrame({"score": score, "label": label}).reset_index()
        n_train = len(dataset.prepare("train", col_set="label"))
        frame = frame[frame.instrument.isin(STOCKS)]
        for r in frame.itertuples():
            rows.append(
                {
                    "analysis_date": date,
                    "feature_date": seg["test"][0].strftime("%Y-%m-%d"),
                    "stock_id": r.instrument,
                    "score": float(r.score),
                    "label": float(r.label),
                    "train_end": seg["valid"][1].strftime("%Y-%m-%d"),
                    "n_train": n_train,
                    "best_iteration": model.model.best_iteration,
                }
            )
        logger.warning(
            "%s/%s %s: trained on %d samples up to %s, %d stocks scored",
            features, universe, date, n_train, seg["valid"][1].date(), len(frame),
        )  # fmt: skip
    return pd.DataFrame(rows)


def run_all(feature_sets, universes, dates, output_dir: Path = OUTPUT_DIR) -> dict:
    """Run (or load cached) predictions for every feature set x universe."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for features in feature_sets:
        for universe in universes:
            path = output_dir / f"predictions_{features}_{universe}.csv"
            if path.exists():
                logger.warning("Cache hit: %s", path)
                out[(features, universe)] = pd.read_csv(path)
                continue
            preds = run_model(features, universe, dates)
            preds.to_csv(path, index=False)
            out[(features, universe)] = preds
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--features", nargs="+", default=list(FEATURE_SETS), choices=FEATURE_SETS)
    parser.add_argument("--universe", nargs="+", default=UNIVERSES, choices=UNIVERSES)
    parser.add_argument("--dates", nargs="+", default=None, help="subset of decision dates")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    init_qlib()
    run_all(args.features, args.universe, args.dates or decision_dates(), args.output_dir)
