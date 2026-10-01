"""Minimal reader/writer for qlib's daily binary format.

A qlib provider directory looks like::

    qlib_data/
      calendars/day.txt               one trading date per line (YYYY-MM-DD)
      instruments/<universe>.txt      TICKER<TAB>start<TAB>end per membership window
      features/<ticker>/<field>.day.bin

Each ``.day.bin`` is little-endian float32: the first value is the index (in ``day.txt``) of the
first date stored, followed by one value per consecutive calendar date (NaN = missing).
"""

from pathlib import Path

import numpy as np
import pandas as pd

DTYPE = "<f4"


def read_calendar(qlib_dir: Path) -> pd.DatetimeIndex:
    lines = (Path(qlib_dir) / "calendars" / "day.txt").read_text().split()
    return pd.DatetimeIndex(pd.to_datetime(lines))


def write_calendar(qlib_dir: Path, calendar: pd.DatetimeIndex) -> None:
    path = Path(qlib_dir) / "calendars" / "day.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(d.strftime("%Y-%m-%d") for d in calendar) + "\n")


def read_bin(path: Path, calendar: pd.DatetimeIndex) -> pd.Series:
    """Read a .day.bin file as a date-indexed float Series."""
    raw = np.fromfile(path, dtype=DTYPE)
    if raw.size <= 1:
        return pd.Series(dtype="float32")
    start = int(raw[0])
    values = raw[1:]
    return pd.Series(values, index=calendar[start : start + len(values)])


def write_bin(path: Path, series: pd.Series, calendar: pd.DatetimeIndex) -> None:
    """Write a date-indexed Series aligned to ``calendar`` (dates outside it are dropped).

    The stored span goes from the first to the last non-NaN value; gaps in between stay NaN.
    """
    s = series.reindex(calendar).astype("float32")
    valid = np.flatnonzero(s.notna().to_numpy())
    if valid.size == 0:
        return
    first, last = valid[0], valid[-1]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.concatenate([[np.float32(first)], s.to_numpy()[first : last + 1]]).astype(DTYPE).tofile(path)
