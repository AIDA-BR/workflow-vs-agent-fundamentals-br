"""Export the subset of the fin-difusion qlib bundle used by this baseline to data/qlib_data.

Only maintainers need this script: readers just unzip the committed ``data/qlib_data.zip``.
It keeps the calendar between CAL_START and CAL_END, the tickers of the training universes,
and the price + fundamental fields listed below, then writes ``data/qlib_data.zip``.

    uv run export_bundle.py --source ~/workspace/fin-difusion/scripts/qlib/work/extracted/qlib_data
"""

import argparse
import shutil
import zipfile
from pathlib import Path

import pandas as pd

from config import QLIB_DIR, STOCKS
from qlib_io import read_bin, read_calendar, write_bin, write_calendar

CAL_START = "2017-01-02"  # one year of warm-up before TRAIN_START for the 60-day Alpha158 windows
CAL_END = "2026-01-30"  # labels of the last decision date (2025-12-01) need ~1 month ahead

PRICE_FIELDS = ["open", "high", "low", "close", "volume", "change", "factor"]
FUNDAMENTAL_FIELDS = [
    "pe", "pb", "p_ebit", "ps", "p_assets", "p_wc", "p_nla", "ev_ebitda", "ev_ebit",
    "gross_margin", "ebit_margin", "net_margin", "ebit_assets", "roic", "roe",
    "current_ratio", "debt_to_equity", "asset_turnover", "mktcap",
]  # fmt: skip


def read_windows(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t", header=None, names=["ticker", "start", "end"])


def clip_windows(windows: pd.DataFrame) -> pd.DataFrame:
    w = windows[(windows.end >= CAL_START) & (windows.start <= CAL_END)].copy()
    w["start"] = w.start.clip(lower=CAL_START)
    w["end"] = w.end.clip(upper=CAL_END)
    return w


def write_windows(path: Path, windows: pd.DataFrame) -> None:
    windows.sort_values(["ticker", "start"]).to_csv(path, sep="\t", header=False, index=False)


def main(source: Path, dest: Path) -> None:
    src_cal = read_calendar(source)
    cal = src_cal[(src_cal >= CAL_START) & (src_cal <= CAL_END)]

    # Universes: point-in-time liquidity windows + the 9 paper stocks over the whole span.
    liquidity = clip_windows(read_windows(source / "instruments" / "all.txt"))
    paper9 = pd.DataFrame({"ticker": STOCKS, "start": CAL_START, "end": CAL_END})
    broad = pd.concat([liquidity[~liquidity.ticker.isin(STOCKS)], paper9])

    if dest.exists():
        shutil.rmtree(dest)
    write_calendar(dest, cal)
    (dest / "instruments").mkdir(parents=True)
    write_windows(dest / "instruments" / "broad.txt", broad)
    write_windows(dest / "instruments" / "paper9.txt", paper9)
    write_windows(dest / "instruments" / "all.txt", broad)

    tickers = sorted(broad.ticker.unique())
    for ticker in tickers:
        for field in PRICE_FIELDS + FUNDAMENTAL_FIELDS:
            src = source / "features" / ticker.lower() / f"{field}.day.bin"
            if src.exists():
                series = read_bin(src, src_cal)
                write_bin(dest / "features" / ticker.lower() / f"{field}.day.bin", series, cal)
    print(f"Exported {len(tickers)} tickers, {len(cal)} days ({cal[0].date()}..{cal[-1].date()})")

    zip_path = dest.parent / "qlib_data.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(dest.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(dest.parent))
    print(f"Wrote {zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="fin-difusion qlib_data dir")
    parser.add_argument("--dest", type=Path, default=QLIB_DIR)
    args = parser.parse_args()
    main(args.source.expanduser(), args.dest)
