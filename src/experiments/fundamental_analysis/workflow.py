import json
import os
import pandas as pd
import time
from datetime import datetime

from src.db.base_query import ResponseFormat, run_sql_query
from src.experiments import ExperimentMetadata
from src.experiments.fundamental_analysis.config import STOCKS
from src.financial_agents.financial_analyst import (
    DB_ATIVO,
    DB_ATIVO_CIRCULANTE,
    DB_DISPONIBILIDADES,
    DB_DIVIDA_BRUTA,
    DB_EBIT_ANUAL,
    DB_EBIT_TRIMESTRE,
    DB_EBITDA_ANUAL,
    DB_FORNECEDORES,
    DB_LUCRO_BRUTO_ANUAL,
    DB_LUCRO_LIQUIDO_ANUAL,
    DB_LUCRO_LIQUIDO_TRIMESTRE,
    DB_PASSIVO_CIRCULANTE,
    DB_PATRIMONIO_LIQUIDO,
    DB_RECEITA_LIQUIDA_ANUAL,
    DB_RECEITA_LIQUIDA_TRIMESTRE,
    compute_indicators,
)
from src.settings import DB_PATH, PRICE_FILE


def get_total_shares(cnpj: str, date: str, shares_multiplier: float = 1.0) -> float:
    query = f"""
    SELECT TOTAL_SHARES_ISSUED, TOTAL_SHARES_TREASURY
    FROM CVM_SHARE_COMPOSITION
    WHERE CNPJ = '{cnpj}' AND REPORT_DATE = '{date}';"""

    result = run_sql_query(
        {"sql_query": query}, db_path=DB_PATH, response_format=ResponseFormat.DICT
    )
    rows = result.get("report", [])
    if not rows or not isinstance(rows, list):
        return 0.0
    row = rows[0]
    issued = float(row.get("TOTAL_SHARES_ISSUED") or 0)
    treasury = float(row.get("TOTAL_SHARES_TREASURY") or 0)
    return (issued - treasury) * shares_multiplier


def _db_account(
    cnpj: str,
    account: str,
    date: str,
    exerc_order: str = "ÚLTIMO",
    period: str = "any",
) -> float:
    """Returns ACCOUNT_VALUE for a single CVM account, or 0.0 if not found.

    Args:
        period: 'any' (no filter), 'accumulated' (start month = Jan, for DRE ytd),
                'quarterly' (start month != Jan, for isolated quarter in ITRs).
    """
    period_filter = ""
    if period == "accumulated":
        period_filter = "AND strftime('%m', ANALYSIS_START_PERIOD_DATE) = '01'"
    elif period == "quarterly":
        period_filter = "AND strftime('%m', ANALYSIS_START_PERIOD_DATE) != '01'"

    query = f"""
    SELECT ACCOUNT_VALUE FROM DFP_ITR_CVM
    WHERE CNPJ = '{cnpj}' AND REPORT_DATE = '{date}'
      AND ACCOUNT_NUMBER = '{account}' AND EXERC_ORDER = '{exerc_order}'
      {period_filter}
    ORDER BY CAST(VERSION AS INTEGER) DESC LIMIT 1;"""
    result = run_sql_query(
        {"sql_query": query}, db_path=DB_PATH, response_format=ResponseFormat.DICT
    )
    rows = result.get("report", [])
    if not rows or not isinstance(rows, list):
        return 0.0
    return float(rows[0].get("ACCOUNT_VALUE") or 0)


def _db_account_name(cnpj: str, account: str, date: str, exerc_order: str = "ÚLTIMO") -> str:
    """Returns the ACCOUNT_NAME for a given account, or '' if not found."""
    query = f"""
    SELECT ACCOUNT_NAME FROM DFP_ITR_CVM
    WHERE CNPJ = '{cnpj}' AND REPORT_DATE = '{date}'
      AND ACCOUNT_NUMBER = '{account}' AND EXERC_ORDER = '{exerc_order}'
    ORDER BY CAST(VERSION AS INTEGER) DESC LIMIT 1;"""
    result = run_sql_query(
        {"sql_query": query}, db_path=DB_PATH, response_format=ResponseFormat.DICT
    )
    rows = result.get("report", [])
    if not rows or not isinstance(rows, list):
        return ""
    return str(rows[0].get("ACCOUNT_NAME", ""))


def _get_patrimonio_liquido(cnpj: str, date: str) -> float:
    """Returns Patrimônio Líquido (excluding minority interests) for any company structure.

    Standard companies report PL at account 2.03 (minorities at 2.03.09).
    Banks and financial institutions report PL at a higher account (e.g. 2.07),
    with minorities labelled 'Não Controladores' in a subaccount.
    """
    # Fast path: standard structure (2.03 = PL)
    pl_name = _db_account_name(cnpj, "2.03", date)
    if "patrimônio" in pl_name.lower():
        return _db_account(cnpj, "2.03", date) - _db_account(cnpj, "2.03.09", date)

    # Non-standard: search 2.04–2.09 for the PL account
    for suffix in ("04", "05", "06", "07", "08", "09"):
        acc = f"2.{suffix}"
        name = _db_account_name(cnpj, acc, date)
        if "patrimônio" not in name.lower():
            continue
        pl_total = _db_account(cnpj, acc, date)
        # Find the minority-interest subaccount (name contains "não controlador")
        minorities = 0.0
        for sub in ("01", "02", "03", "04", "05", "06", "07", "08", "09"):
            sub_acc = f"{acc}.{sub}"
            sub_name = _db_account_name(cnpj, sub_acc, date)
            if "não controlador" in sub_name.lower():
                minorities = _db_account(cnpj, sub_acc, date)
                break
        return pl_total - minorities

    # Absolute fallback (covers companies with no minorities disclosure)
    return _db_account(cnpj, "2.03", date)


def get_db_fields(cnpj: str, date: str, prev_date: str | None = None) -> dict[str, float]:
    """Fetches all 15 base financial fields directly from the CVM database (DF Consolidado).

    prev_date: deprecated, kept for backward compatibility but ignored — all dates are
    derived internally from `date`.

    Account mapping:
      Ativo                    → 1
      Disponibilidades         → 1.01.01 + 1.01.02
      Ativo Circulante         → 1.01
      Passivo Circulante       → 2.01
      Dív. Bruta               → 2.01.04 + 2.02.01
      Patrim. Líq.             → _get_patrimonio_liquido()  (handles banks: 2.07 instead of 2.03)
      Fornecedores             → 2.01.02
      Receita Líquida (12m)    → TTM: YTD(date) + FY(prev_year_dec31) − YTD(same_period_prev_year)
      Lucro Bruto (12m)        → TTM of 3.03
      EBIT (12m)               → TTM of (3.03 + 3.04.01 + 3.04.02)
      EBITDA (12m)             → TTM EBIT + abs(TTM 7.04.01)  [D&A from DVA]
      Lucro Líquido (12m)      → TTM of 3.11.01 (controladores; fallback 3.11 se zero)
      Receita Líquida (3m)     → YTD(date) − YTD(prev_quarter_end)  [isolated quarter]
      EBIT (3m)                → isolated quarter of (3.03 + 3.04.01 + 3.04.02)
      Lucro Líquido (3m)       → isolated quarter of 3.11.01 (fallback 3.11)

    For DFP reports (month == 12) TTM equals the full-year YTD — no adjustment needed.
    """
    date_dt = datetime.fromisoformat(date) if isinstance(date, str) else date
    year, month, day = date_dt.year, date_dt.month, date_dt.day
    is_annual = month == 12

    # End of the previous quarter (for isolated-quarter calculation)
    if month <= 3:
        prev_quarter = f"{year - 1}-12-31"
    elif month <= 6:
        prev_quarter = f"{year}-03-31"
    elif month <= 9:
        prev_quarter = f"{year}-06-30"
    else:
        prev_quarter = f"{year}-09-30"

    # Dates needed for TTM on ITR reports
    fy_prev = f"{year - 1}-12-31"
    ytd_prev = f"{year - 1}-{month:02d}-{day:02d}"

    def _ttm(account: str) -> float:
        """Trailing Twelve Months for a single income-statement account.

        DFP (annual): value is already 12 months — return as-is.
        ITR (quarterly): TTM = YTD_current + FY_prev_year − YTD_same_period_prev_year
        """
        ytd_current = _db_account(cnpj, account, date, period="accumulated")
        if is_annual:
            return ytd_current
        return (
            ytd_current
            + _db_account(cnpj, account, fy_prev)
            - _db_account(cnpj, account, ytd_prev, period="accumulated")
        )

    def _ttm_controlling(account_ctrl: str, account_total: str) -> float:
        """TTM for a controlling-shareholders account, falling back to total if zero.

        Market convention (Fundamentus, etc.) uses the portion attributable to
        controlling shareholders (e.g. 3.11.01) for LPA/ROE/P/L. Falls back to
        the consolidated total (e.g. 3.11) for companies with no minority interests
        (where 3.11.01 == 3.11).

        Consistency check: only uses account_ctrl if that sub-account is populated
        in ALL periods required for the TTM calculation. Some companies report
        3.11.01 in ITR but not in DFP (or vice-versa); mixing them produces a
        wrong TTM (e.g. YTD_current + 0 − YTD_prev ≠ real TTM).
        """
        if is_annual:
            ctrl_val = _db_account(cnpj, account_ctrl, date, period="accumulated")
            return ctrl_val if ctrl_val != 0.0 else _ttm(account_total)

        ctrl_ytd = _db_account(cnpj, account_ctrl, date, period="accumulated")
        ctrl_fy_prev = _db_account(cnpj, account_ctrl, fy_prev)
        ctrl_ytd_prev = _db_account(cnpj, account_ctrl, ytd_prev, period="accumulated")
        if ctrl_ytd != 0.0 and ctrl_fy_prev != 0.0 and ctrl_ytd_prev != 0.0:
            return ctrl_ytd + ctrl_fy_prev - ctrl_ytd_prev
        return _ttm(account_total)

    def _ttm_sum(*accounts: str) -> float:
        return sum(_ttm(acc) for acc in accounts)

    def _quarter(account: str) -> float:
        """Isolated current quarter = YTD(date) − YTD(prev_quarter_end).

        Special case — Q1 (March 31 ITR): prev_quarter is Dec 31 of the prior
        year, which holds a full-year (12-month) DFP value.  Subtracting it
        from the 3-month Q1 YTD would yield a large negative number.
        For Q1 the YTD *is* the isolated quarter, so we return it directly.
        """
        if month <= 3:
            return _db_account(cnpj, account, date, period="accumulated")
        return _db_account(cnpj, account, date, period="accumulated") - _db_account(
            cnpj, account, prev_quarter, period="accumulated"
        )

    def _quarter_sum(*accounts: str) -> float:
        return sum(_quarter(acc) for acc in accounts)

    # --- Balance sheet (point-in-time, no TTM needed) ---
    ativo = _db_account(cnpj, "1", date)
    disponibilidades = _db_account(cnpj, "1.01.01", date) + _db_account(cnpj, "1.01.02", date)
    ativo_circulante = _db_account(cnpj, "1.01", date)
    passivo_circulante = _db_account(cnpj, "2.01", date)
    divida_bruta = _db_account(cnpj, "2.01.04", date) + _db_account(cnpj, "2.02.01", date)
    patrimonio_liquido = _get_patrimonio_liquido(cnpj, date)
    fornecedores = _db_account(cnpj, "2.01.02", date)

    # --- Income statement — 12-month TTM ---
    receita_liquida_anual = _ttm("3.01")
    lucro_bruto_anual = _ttm("3.03")
    ebit_anual = _ttm_sum("3.03", "3.04.01", "3.04.02")
    ebitda_anual = ebit_anual + abs(_ttm("7.04.01"))
    lucro_liquido_anual = _ttm_controlling("3.11.01", "3.11")

    # --- Income statement — isolated quarter ---
    receita_liquida_trimestre = _quarter("3.01")
    ebit_trimestre = _quarter_sum("3.03", "3.04.01", "3.04.02")
    # Use 3.11.01 (controladores) for the isolated quarter only if the sub-account
    # is available in BOTH the current and previous-quarter periods; otherwise fall
    # back to 3.11 (total) to avoid a spurious result from an incomplete subtraction.
    # Q1 special case: prev_quarter is the prior-year DFP (12m), so we only use
    # curr_quarter_ctrl directly (same rationale as _quarter above).
    curr_quarter_ctrl = _db_account(cnpj, "3.11.01", date, period="accumulated")
    if month <= 3:
        lucro_liquido_trimestre = (
            curr_quarter_ctrl if curr_quarter_ctrl != 0.0 else _quarter("3.11")
        )
    else:
        prev_quarter_ctrl = _db_account(cnpj, "3.11.01", prev_quarter, period="accumulated")
        if curr_quarter_ctrl != 0.0 and prev_quarter_ctrl != 0.0:
            lucro_liquido_trimestre = curr_quarter_ctrl - prev_quarter_ctrl
        else:
            lucro_liquido_trimestre = _quarter("3.11")

    return {
        DB_ATIVO: ativo,
        DB_DISPONIBILIDADES: disponibilidades,
        DB_ATIVO_CIRCULANTE: ativo_circulante,
        DB_PASSIVO_CIRCULANTE: passivo_circulante,
        DB_DIVIDA_BRUTA: divida_bruta,
        DB_PATRIMONIO_LIQUIDO: patrimonio_liquido,
        DB_FORNECEDORES: fornecedores,
        DB_RECEITA_LIQUIDA_ANUAL: receita_liquida_anual,
        DB_LUCRO_BRUTO_ANUAL: lucro_bruto_anual,
        DB_EBIT_ANUAL: ebit_anual,
        DB_EBITDA_ANUAL: ebitda_anual,
        DB_LUCRO_LIQUIDO_ANUAL: lucro_liquido_anual,
        DB_RECEITA_LIQUIDA_TRIMESTRE: receita_liquida_trimestre,
        DB_EBIT_TRIMESTRE: ebit_trimestre,
        DB_LUCRO_LIQUIDO_TRIMESTRE: lucro_liquido_trimestre,
    }


def run(experiment_metadata: ExperimentMetadata, n_times: int = 3):
    write_folder = f"{experiment_metadata.write_folder}/workflow"
    os.makedirs(write_folder, exist_ok=True)
    with open(f"{write_folder}/experiment_metadata.json", "w") as f:
        json.dump(experiment_metadata.model_dump(), f, indent=4)

    price_df = pd.read_csv(PRICE_FILE)
    for stock in STOCKS:
        cnpj, stock_id = stock.cnpj, stock.stock_id
        price = float(price_df[price_df["Papel"] == stock_id].iloc[0]["Cotação"])

        for experiment_id in range(n_times):
            if os.path.exists(f"{write_folder}/{stock_id}_{experiment_id}.json"):
                continue
            print(stock, experiment_id)
            start = time.time()
            db_fields = get_db_fields(cnpj=cnpj, date="2024-12-31")
            total_shares = get_total_shares(
                cnpj=cnpj, date="2024-12-31", shares_multiplier=stock.shares_multiplier
            )
            output = compute_indicators(db_fields=db_fields, price=price, total_shares=total_shares)
            end = time.time()

            output_dict = output.model_dump()
            result = {
                "usage": {"requests": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                "steps": [],
                "time": end - start,
                "output": output_dict,
            }
            with open(f"{write_folder}/{stock_id}_{experiment_id}.json", "w") as f:
                json.dump(result, f, indent=4)
            with open(f"{write_folder}/{stock_id}_output_{experiment_id}.json", "w") as f:
                json.dump(output_dict, f, indent=4)
