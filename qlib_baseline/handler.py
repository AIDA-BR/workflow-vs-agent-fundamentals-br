"""qlib data handler: Alpha158 price/volume factors plus optional extra fields."""

from qlib.contrib.data.handler import Alpha158
from qlib.contrib.data.loader import Alpha158DL

from config import LABEL


class Alpha158Plus(Alpha158):
    """Alpha158 without VWAP (the B3 bundle has no ``$vwap`` field) plus ``extra_fields``.

    ``extra_fields`` is a list of (qlib expression, column name), e.g. ``[("$roe", "ROE")]``.
    Any ``$field`` in an expression must exist as ``features/<ticker>/<field>.day.bin``.
    """

    def __init__(self, extra_fields=(), **kwargs):
        self.extra_fields = list(extra_fields)
        super().__init__(**kwargs)

    def get_feature_config(self):
        conf = {
            "kbar": {},
            "price": {"windows": [0], "feature": ["OPEN", "HIGH", "LOW"]},
            "rolling": {},
        }
        fields, names = Alpha158DL.get_feature_config(conf)
        if self.extra_fields:
            extra_fields, extra_names = zip(*self.extra_fields)
            fields, names = fields + list(extra_fields), names + list(extra_names)
        return fields, names


def build_handler(universe: str, extra_fields, start_time: str, end_time: str) -> Alpha158Plus:
    """Load features + label once for the whole period.

    Only stateless processors are used (no normalisation fitted on a time range), so the same
    handler can be sliced into many walk-forward folds without look-ahead. LightGBM is
    scale-invariant and handles NaN natively, so features are left un-normalised; the label is kept
    raw so predictions read as expected 1-month returns.
    """
    return Alpha158Plus(
        extra_fields=extra_fields,
        instruments=universe,
        start_time=start_time,
        end_time=end_time,
        infer_processors=[{"class": "ProcessInf", "kwargs": {}}],
        learn_processors=[{"class": "DropnaLabel"}],
        label=(LABEL, ["LABEL0"]),
    )
