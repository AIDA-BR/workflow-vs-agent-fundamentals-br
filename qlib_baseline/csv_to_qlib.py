"""Add new features from a CSV to the qlib dataset (e.g. environmental / ESG factors).

The CSV is in "long" format — one row per (date, ticker), one column per feature:

    date,ticker,env_score,co2_intensity
    2023-03-31,PETR4,61.2,0.84
    2023-03-31,VALE3,55.0,1.12
    2023-06-30,PETR4,62.0,0.80
    ...

* ``date`` must be the date the value became **public** (not the period it refers to), otherwise
  the model sees the future. If you only have reference dates, use ``--lag-days`` to delay them.
* Values are aligned to the trading calendar and forward-filled until the next observation
  (optionally at most ``--ffill-limit`` trading days), so quarterly / yearly data works.
* Each column ``<col>`` becomes ``features/<ticker>/<col>.day.bin`` and is available in qlib as
  ``$<col>`` — add ``("$<col>", "<NAME>")`` to ``EXTRA_FEATURES`` in config.py to use it.

    uv run csv_to_qlib.py ../data/custom_features_example.csv
    uv run csv_to_qlib.py my_factors.csv --columns env_score --lag-days 30 --ffill-limit 252
"""

import argparse
import re
from pathlib import Path

import pandas as pd

from config import QLIB_DIR
from qlib_io import read_calendar, write_bin

PROTECTED = {"open", "high", "low", "close", "volume", "change", "factor"}


def convert(
    csv_path: Path,
    qlib_dir: Path = QLIB_DIR,
    columns: list[str] | None = None,
    lag_days: int = 0,
    ffill_limit: int | None = None,
    overwrite: bool = False,
) -> list[str]:
    df = pd.read_csv(csv_path)
    missing = {"date", "ticker"} - set(df.columns)
    if missing:
        raise SystemExit(f"CSV must have columns 'date' and 'ticker' (missing: {missing})")
    columns = columns or [c for c in df.columns if c not in ("date", "ticker")]
    for col in columns:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", col):
            raise SystemExit(f"column {col!r}: use lower-case letters, digits and '_' only")
        if col in PROTECTED and not overwrite:
            raise SystemExit(f"column {col!r} would overwrite a price field (use --overwrite)")

    calendar = read_calendar(qlib_dir)
    df["date"] = pd.to_datetime(df["date"]) + pd.Timedelta(days=lag_days)
    df["ticker"] = df["ticker"].str.upper().str.strip()

    written = []
    for ticker, group in df.groupby("ticker"):
        feature_dir = qlib_dir / "features" / ticker.lower()
        if not feature_dir.exists():
            print(f"WARNING: {ticker} is not in the bundle (no price data) — skipped")
            continue
        group = group.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
        for col in columns:
            obs = pd.to_numeric(group[col], errors="coerce").dropna()
            if obs.empty:
                continue
            # A value published on a non-trading day becomes visible on the next trading day.
            pos = calendar.searchsorted(obs.index)
            keep = pos < len(calendar)
            visible = pd.Series(obs.to_numpy()[keep], index=pos[keep])
            visible = visible[~visible.index.duplicated(keep="last")]
            values = visible.reindex(range(len(calendar))).ffill(limit=ffill_limit)
            aligned = pd.Series(values.to_numpy(), index=calendar)
            write_bin(feature_dir / f"{col}.day.bin", aligned, calendar)
            written.append(f"{ticker}:{col}")
    print(f"Wrote {len(written)} series ({len(columns)} columns) to {qlib_dir}/features")
    print("Use them in config.py, e.g.: EXTRA_FEATURES = [" +
          ", ".join(f'("${c}", "{c.upper()}")' for c in columns) + "]")  # fmt: skip
    return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("csv", type=Path)
    parser.add_argument("--qlib-dir", type=Path, default=QLIB_DIR)
    parser.add_argument("--columns", nargs="+", help="subset of CSV columns to convert")
    parser.add_argument(
        "--lag-days", type=int, default=0, help="delay every date by N calendar days"
    )
    parser.add_argument(
        "--ffill-limit", type=int, default=None, help="max trading days to carry a value"
    )
    parser.add_argument("--overwrite", action="store_true", help="allow overwriting price fields")
    a = parser.parse_args()
    convert(a.csv, a.qlib_dir, a.columns, a.lag_days, a.ffill_limit, a.overwrite)
