import json
import os
import pandas as pd
import time

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


def get_total_shares(cnpj: str, date: str) -> float:
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
    return issued - treasury


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


def get_db_fields(cnpj: str, date: str, prev_date: str) -> dict[str, float]:
    """Fetches all 15 base financial fields directly from the CVM database (DF Consolidado).

    Account mapping:
      Ativo                    → 1
      Disponibilidades         → 1.01.01 + 1.01.02
      Ativo Circulante         → 1.01
      Passivo Circulante       → 2.01
      Dív. Bruta               → 2.01.04 + 2.02.01
      Patrim. Líq.             → _get_patrimonio_liquido()  (handles banks: 2.07 instead of 2.03)
      Fornecedores             → 2.01.02
      Receita Líquida (12m)    → 3.01
      Lucro Bruto (12m)        → 3.03
      EBIT (12m)               → 3.03 + 3.04.01 + 3.04.02
      EBITDA (12m)             → EBIT + abs(7.04.01)  (D&A da DVA)
      Lucro Líquido (12m)      → 3.11  (total consolidado, incluindo minoritários)
      Receita Líquida (3m)     → 3.01 DFP − 3.01 ITR acumulado
      EBIT (3m)                → (3.03 + 3.04.01 + 3.04.02) DFP − ITR acumulado
      Lucro Líquido (3m)       → 3.11 DFP − 3.11 ITR acumulado
    """
    ativo = _db_account(cnpj, "1", date)
    disponibilidades = _db_account(cnpj, "1.01.01", date) + _db_account(cnpj, "1.01.02", date)
    ativo_circulante = _db_account(cnpj, "1.01", date)
    passivo_circulante = _db_account(cnpj, "2.01", date)
    divida_bruta = _db_account(cnpj, "2.01.04", date) + _db_account(cnpj, "2.02.01", date)
    patrimonio_liquido = _get_patrimonio_liquido(cnpj, date)
    fornecedores = _db_account(cnpj, "2.01.02", date)

    receita_liquida_anual = _db_account(cnpj, "3.01", date)
    lucro_bruto_anual = _db_account(cnpj, "3.03", date)
    ebit_anual = (
        _db_account(cnpj, "3.03", date)
        + _db_account(cnpj, "3.04.01", date)
        + _db_account(cnpj, "3.04.02", date)
    )
    ebitda_anual = ebit_anual + abs(_db_account(cnpj, "7.04.01", date))
    lucro_liquido_anual = _db_account(cnpj, "3.11", date)

    receita_liquida_trimestre = _db_account(cnpj, "3.01", date) - _db_account(
        cnpj, "3.01", prev_date, period="accumulated"
    )
    ebit_trimestre = (
        _db_account(cnpj, "3.03", date)
        + _db_account(cnpj, "3.04.01", date)
        + _db_account(cnpj, "3.04.02", date)
    ) - (
        _db_account(cnpj, "3.03", prev_date, period="accumulated")
        + _db_account(cnpj, "3.04.01", prev_date, period="accumulated")
        + _db_account(cnpj, "3.04.02", prev_date, period="accumulated")
    )
    lucro_liquido_trimestre = _db_account(cnpj, "3.11", date) - _db_account(
        cnpj, "3.11", prev_date, period="accumulated"
    )

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
            db_fields = get_db_fields(cnpj=cnpj, date="2024-12-31", prev_date="2024-09-30")
            total_shares = get_total_shares(cnpj=cnpj, date="2024-12-31")
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
