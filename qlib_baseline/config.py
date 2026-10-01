"""Shared configuration for the qlib baseline.

Everything an experiment needs to agree with the ICAIF 2026 setup lives here: the 9 stocks, the
24 monthly decision dates, the label horizon, the LightGBM hyper-parameters and the feature sets.
To try new features (e.g. environmental factors), add them to ``EXTRA_FEATURES`` or create a new
entry in ``FEATURE_SETS`` — see ``qlib_baseline/README.md``.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
QLIB_DIR = REPO_ROOT / "data" / "qlib_data"
RESULTS_DIR = REPO_ROOT / "results"

#: The paper's 9 stocks (qlib instrument names are upper-case; feature folders are lower-case).
STOCKS = ["ALUP11", "AURE3", "CPLE3", "EALT4", "ENEV3", "EQTL3", "PETR4", "RECV3", "VALE3"]

#: Folder whose decisions/prices define the paper's trading calendar. Prices for the qlib
#: strategies are copied from here so every strategy trades at exactly the same COTAHIST close.
REFERENCE_FOLDER = RESULTS_DIR / "sem_fato_relevante_gpt5mini"


def decision_dates() -> list[str]:
    """The 24 monthly decision dates of the paper (first business day of each month)."""
    with open(REFERENCE_FOLDER / "decisions_sample.json") as f:
        decisions = json.load(f)
    return sorted({d["analysis_date"] for d in decisions})


#: Label: return from the close of the trading day after the feature date (= the decision day D,
#: when features are taken at D-1) to the close ~1 month (HORIZON trading days) later.
HORIZON = 21
LABEL = [f"Ref($close, -{HORIZON + 1})/Ref($close, -1) - 1"]

#: First date used for training. Fundamentals in the bundle start on 2021-03-31 and are NaN before
#: (LightGBM handles missing values natively).
TRAIN_START = "2018-01-01"
#: The last VALID_MONTHS of each training window are held out for early stopping.
VALID_MONTHS = 6

#: Hyper-parameters copied from fin-difusion/scripts/qlib/train.py.
LGB_PARAMS = dict(
    loss="mse",
    learning_rate=0.01,
    num_leaves=31,
    max_depth=6,
    min_data_in_leaf=100,
    feature_fraction=0.7,
    bagging_fraction=0.8,
    bagging_freq=5,
    lambda_l1=0.1,
    lambda_l2=1.0,
    early_stopping_rounds=100,
    num_boost_round=2000,
    seed=42,
)

#: Bundle fields equivalent to the paper's rule-based fundamental indicators
#: (src/financial_agents/financial_analyst.py::compute_indicators). (expression, column name).
FUNDAMENTAL_FEATURES = [
    ("$pe", "P_L"),  # P/L
    ("$pb", "P_VP"),  # P/VP
    ("$p_ebit", "P_EBIT"),  # P/EBIT
    ("$ps", "PSR"),  # PSR
    ("$p_assets", "P_ATIVOS"),  # P/Ativos
    ("$p_wc", "P_CAP_GIRO"),  # P/Cap. Giro
    ("$p_nla", "P_ATIV_CIRC_LIQ"),  # P/Ativ Circ Liq
    ("$ev_ebitda", "EV_EBITDA"),  # EV/EBITDA
    ("$ev_ebit", "EV_EBIT"),  # EV/EBIT
    ("$gross_margin", "MARG_BRUTA"),  # Marg. Bruta
    ("$ebit_margin", "MARG_EBIT"),  # Marg. EBIT
    ("$net_margin", "MARG_LIQUIDA"),  # Marg. Líquida
    ("$ebit_assets", "EBIT_ATIVO"),  # EBIT/Ativo
    ("$roic", "ROIC"),  # ROIC
    ("$roe", "ROE"),  # ROE
    ("$current_ratio", "LIQUIDEZ_CORR"),  # Liquidez Corr
    ("$debt_to_equity", "DIV_BR_PATRIM"),  # Div Br/Patrim
    ("$asset_turnover", "GIRO_ATIVOS"),  # Giro Ativos
    ("Log($mktcap+1)", "LOG_MKTCAP"),  # size (Valor de mercado)
]

#: Hook for new features (e.g. environmental factors). Each entry is (qlib expression, name), e.g.
#: ("$esg_score", "ESG_SCORE") after running csv_to_qlib.py on a CSV with an ``esg_score`` column.
EXTRA_FEATURES: list[tuple[str, str]] = []

#: Feature sets on top of Alpha158 (price/volume). Add a new key to train an extra model.
FEATURE_SETS = {
    "price": [],
    "fundamentals": FUNDAMENTAL_FEATURES,
}

#: Training universes (files in data/qlib_data/instruments/). Decisions are always for STOCKS.
#: broad  = point-in-time B3 liquidity universe (top-100 by traded value, re-ranked every
#:          4 months) plus the 9 paper stocks for the whole period.
#: paper9 = only the 9 paper stocks.
UNIVERSES = ["broad", "paper9"]

#: Decision rules mapping the predicted 1-month return to Comprar / Vender / Manter.
THRESHOLD = 0.0  # threshold rule: buy if score > +THRESHOLD, sell if score < -THRESHOLD
TOP_K = 3  # rank rule: buy the TOP_K best-ranked of the 9 stocks, sell the TOP_K worst
RULES = ["threshold", "rank"]
