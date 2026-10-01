"""Trading evaluation — the functions of manager_evaluation.ipynb (cells 3, 4 and 6), copied verbatim.

Keeping them identical guarantees that the qlib strategies are scored exactly like Table 1 of the
paper: monthly Comprar / Vender / Manter decisions, trades at the COTAHIST close of the decision day,
Norm. Return = sum(sell - avg_buy) / sum(avg_buy) (the paper's "trading return"), and Sharpe
annualised with SELIC = 15%.
"""

import json
import os
from datetime import datetime

import numpy as np

SELIC = 0.15


def compute_portfolio_returns(decisions: list, results: list, stocks_filter: set = None) -> dict:
    """Simulate portfolio trades and return realized trade data per stock.

    - 'Comprar' opens (or adds to) a position at the day's closing price.
    - 'Vender' closes all open positions; trade return = (sell - avg_buy) / avg_buy.
    Remaining open positions are closed at the last observed price.

    Returns per stock: {'pct': [...], 'gross': [...], 'buy': [...]}.
    """
    price_lookup = {(r["ACAO"], r["DATA_DO_PREGAO"]): r["PRECO_ULTIMO_NEGOCIO"] for r in results}

    open_positions: dict[str, list] = {}
    trade_data: dict[str, dict] = {}
    last_price: dict[str, float] = {}

    for decision in decisions:
        stock_id = decision["stock_id"]

        if stocks_filter and stock_id not in stocks_filter:
            continue

        date = decision["analysis_date"]
        rec = decision["recommendation"]
        price = price_lookup[(stock_id, date)]

        last_price[stock_id] = price
        open_positions.setdefault(stock_id, [])
        trade_data.setdefault(stock_id, {"pct": [], "gross": [], "buy": []})

        if rec == "Comprar":
            open_positions[stock_id].append(price)
        elif rec == "Vender" and open_positions[stock_id]:
            avg_buy = np.mean(open_positions[stock_id])
            trade_data[stock_id]["pct"].append((price - avg_buy) / avg_buy)
            trade_data[stock_id]["gross"].append(price - avg_buy)
            trade_data[stock_id]["buy"].append(avg_buy)
            open_positions[stock_id] = []

    # Close any remaining open positions at last known price
    for stock_id, positions in open_positions.items():
        if positions:
            avg_buy = np.mean(positions)
            price = last_price[stock_id]
            trade_data[stock_id]["pct"].append((price - avg_buy) / avg_buy)
            trade_data[stock_id]["gross"].append(price - avg_buy)
            trade_data[stock_id]["buy"].append(avg_buy)

    return trade_data


def compute_buy_and_hold(results: list, stocks_filter: set = None) -> dict:
    """Buy at the first observed closing price and sell at the last (one trade per stock)."""
    prices_per_stock: dict[str, list] = {}
    for r in results:
        stock_id = r["ACAO"]
        if stocks_filter and stock_id not in stocks_filter:
            continue
        prices_per_stock.setdefault(stock_id, [])
        prices_per_stock[stock_id].append(r["PRECO_ULTIMO_NEGOCIO"])

    data = {}
    for stock_id, prices in prices_per_stock.items():
        if len(prices) >= 2:
            first, last = prices[0], prices[-1]
            data[stock_id] = {
                "pct": [(last - first) / first],
                "gross": [last - first],
                "buy": [first],
            }
    return data


def total_return_pct(data: dict) -> float:
    """Sum of all % trade returns across all stocks (original metric)."""
    return sum(sum(v["pct"]) for v in data.values())


def stock_return_norm(data: dict, stock: str) -> float:
    """Normalized return for one stock: sum(gross) / sum(avg_buy)."""
    d = data.get(stock, {"gross": [], "buy": []})
    buy_sum = sum(d["buy"])
    return sum(d["gross"]) / buy_sum if buy_sum else 0.0


def total_return_norm(data: dict) -> float:
    """Portfolio normalized return: sum(all gross) / sum(all avg_buy)."""
    gross_all = sum(sum(v["gross"]) for v in data.values())
    buy_all = sum(sum(v["buy"]) for v in data.values())
    return gross_all / buy_all if buy_all else 0.0


def compute_sharpe(data: dict, n_trading_days: int, annual_risk_free: float = SELIC) -> float:
    """Annualized Sharpe Ratio based on individual trade % returns (ddof=1)."""
    all_pct = [r for v in data.values() for r in v["pct"]]
    if len(all_pct) < 2:
        return float("nan")

    n_trades = len(all_pct)
    n_per_year = n_trades * (252 / n_trading_days)
    mean_r = np.mean(all_pct)
    std_r = np.std(all_pct, ddof=1)

    annualized_return = mean_r * n_per_year
    annualized_std = std_r * np.sqrt(n_per_year)
    return (annualized_return - annual_risk_free) / annualized_std


# ---------------------------------------------------------------------------
# Helpers for the qlib notebook
# ---------------------------------------------------------------------------


def load(folder) -> tuple:
    if not os.path.exists(f"{folder}/decisions_sample.json"):
        print(f"WARNING: {folder} not found — strategy will be reported as empty")
        return [], []
    with open(f"{folder}/decisions_sample.json") as f:
        decisions = json.load(f)
    with open(f"{folder}/results_sample.json") as f:
        results = json.load(f)
    return decisions, results


def n_days(decisions: list) -> int:
    """Calendar days between the first and last decision (the notebook's n_trading_days)."""
    dates = [datetime.fromisoformat(d["analysis_date"]) for d in decisions]
    return (max(dates) - min(dates)).days


def summarize(name: str, data: dict, n_trading_days: int, n_stocks: int = 9) -> dict:
    pct = [r for v in data.values() for r in v["pct"]]
    return {
        "Strategy": name,
        "Norm. Return": total_return_norm(data),
        "Sharpe": compute_sharpe(data, n_trading_days),
        "Trading Return": total_return_pct(data),
        "Avg/Stock": total_return_pct(data) / n_stocks,
        "# Trades": len(pct),
        "Win rate": float(np.mean([p > 0 for p in pct])) if pct else float("nan"),
    }
