import asyncio
import json
import os
import pandas as pd
import time

from agents import Agent, ModelSettings, Runner, RunResult
from openai.types.shared import Reasoning

from src.db.base_query import ResponseFormat, run_sql_query
from src.experiments import ExperimentMetadata
from src.experiments.fundamental_analysis.config import STOCKS
from src.experiments.utils import save_results
from src.financial_agents import get_agent
from src.financial_agents.financial_analyst import (
    DB_ATIVO,
    DB_ATIVO_CIRCULANTE,
    DB_DISPONIBILIDADES,
    DB_DIVIDA_BRUTA,
    DB_LUCRO_BRUTO_ANUAL,
    DB_PASSIVO_CIRCULANTE,
    DB_RECEITA_LIQUIDA_ANUAL,
    DB_RECEITA_LIQUIDA_TRIMESTRE,
    FINANCIAL_ANALYST_INSTRUCTION,
    RawIndicator,
    RawIndicatorOutput,
    compute_indicators,
)
from src.settings import DB_PATH, PRICE_FILE

TEMPLATE_INPUT = """Extrair indicadores financeiros brutos da empresa {name} (CNPJ {cnpj}) em Dezembro de 2024.

# Relatório DFP/ITR de Dezembro de 2024
{report}

# Composição de ativos de Dezembro de 2024
{composition}

# Relatório DFP/ITR do Trimestre Anterior
{previous_report}

Feedback: {feedback}"""


def init_agent(experiment_metadata: ExperimentMetadata) -> Agent:
    model_settings = ModelSettings(tool_choice="required")
    if experiment_metadata.reasoning:
        reasoning = Reasoning(effort=experiment_metadata.reasoning)
        model_settings = ModelSettings(
            reasoning=reasoning,
            verbosity=experiment_metadata.verbosity,
        )

    return get_agent(
        name="financial_analyst",
        instructions=FINANCIAL_ANALYST_INSTRUCTION,
        tools=[],
        servers=[],
        model=experiment_metadata.model,
        model_settings=model_settings,
        output_type=RawIndicatorOutput,
    )


def get_stock_report(cnpj: str, date: str) -> str:
    query = f"""
    SELECT ACCOUNT_NUMBER, ACCOUNT_NAME, ACCOUNT_VALUE, VERSION, EXERC_ORDER, ANALYSIS_START_PERIOD_DATE, ANALYSIS_END_PERIOD_DATE
    FROM DFP_ITR_CVM
    WHERE CNPJ = '{cnpj}' AND REPORT_DATE = '{date}'
    ORDER BY ACCOUNT_NUMBER;"""

    result = run_sql_query({"sql_query": query}, db_path=DB_PATH)
    return result.get("report", "")


def get_stock_composition(cnpj: str, date: str) -> str:
    query = f"""
    SELECT
        REPORT_DATE,
        COMPANY_NAME,
        ORDINARY_SHARES_ISSUED,
        ORDINARY_SHARES_TREASURY,
        PREFERRED_SHARES_ISSUED,
        PREFERRED_SHARES_TREASURY,
        TOTAL_SHARES_ISSUED,
        TOTAL_SHARES_TREASURY
    FROM CVM_SHARE_COMPOSITION
    WHERE CNPJ = '{cnpj}' AND REPORT_DATE = '{date}';"""

    result = run_sql_query({"sql_query": query}, db_path=DB_PATH)
    return result.get("report", "")


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


def _db_account(cnpj: str, account: str, date: str) -> float:
    """Returns ACCOUNT_VALUE for a single CVM account (EXERC_ORDER='ÚLTIMO'), or 0.0."""
    query = f"""
    SELECT ACCOUNT_VALUE FROM DFP_ITR_CVM
    WHERE CNPJ = '{cnpj}' AND REPORT_DATE = '{date}'
      AND ACCOUNT_NUMBER = '{account}' AND EXERC_ORDER = 'ÚLTIMO';"""
    result = run_sql_query(
        {"sql_query": query}, db_path=DB_PATH, response_format=ResponseFormat.DICT
    )
    rows = result.get("report", [])
    if not rows or not isinstance(rows, list):
        return 0.0
    return float(rows[0].get("ACCOUNT_VALUE") or 0)


def get_db_fields(cnpj: str, date: str, prev_date: str) -> dict[str, float]:
    """Fetches the 8 base financial fields directly from the CVM database.

    These fields have standardized account numbers across all companies and match
    the gold reference data with < 0.2% error (balance sheet) and < 0.1% error (revenue).
    The LLM is therefore not asked to extract them.

    Account mapping:
      Ativo                   → 1
      Disponibilidades        → 1.01.01 + 1.01.02
      Ativo Circulante        → 1.01
      Passivo Circulante      → 2.01
      Dív. Bruta              → 2.01.04 + 2.02.01
      Receita Líquida (12m)   → 3.01  (ÚLTIMO, DFP date)
      Lucro Bruto (12m)       → 3.03  (ÚLTIMO, DFP date)
      Receita Líquida (3m)    → 3.01 DFP − 3.01 ITR  (quarterly subtraction)
    """
    ativo = _db_account(cnpj, "1", date)
    disponibilidades = _db_account(cnpj, "1.01.01", date) + _db_account(cnpj, "1.01.02", date)
    ativo_circulante = _db_account(cnpj, "1.01", date)
    passivo_circulante = _db_account(cnpj, "2.01", date)
    divida_bruta = _db_account(cnpj, "2.01.04", date) + _db_account(cnpj, "2.02.01", date)
    receita_liquida_anual = _db_account(cnpj, "3.01", date)
    lucro_bruto_anual = _db_account(cnpj, "3.03", date)
    receita_liquida_trimestre = _db_account(cnpj, "3.01", date) - _db_account(
        cnpj, "3.01", prev_date
    )

    return {
        DB_ATIVO: ativo,
        DB_DISPONIBILIDADES: disponibilidades,
        DB_ATIVO_CIRCULANTE: ativo_circulante,
        DB_PASSIVO_CIRCULANTE: passivo_circulante,
        DB_DIVIDA_BRUTA: divida_bruta,
        DB_RECEITA_LIQUIDA_ANUAL: receita_liquida_anual,
        DB_LUCRO_BRUTO_ANUAL: lucro_bruto_anual,
        DB_RECEITA_LIQUIDA_TRIMESTRE: receita_liquida_trimestre,
    }


def analyse(
    agent: Agent,
    name: str,
    cnpj: str,
    price: str,
    report: str,
    composition: str,
    previous_report: str,
    experiment_metadata: ExperimentMetadata,
) -> RunResult:
    feedback = "Extraia todos os indicadores financeiros brutos disponíveis no relatório"

    inp_data = TEMPLATE_INPUT.format(
        name=name,
        cnpj=cnpj,
        price_str=price,
        report=report,
        composition=composition,
        previous_report=previous_report,
        feedback=feedback,
    )

    return asyncio.run(Runner.run(agent, input=inp_data, max_turns=experiment_metadata.max_turns))


def guardrail(
    agent: Agent,
    name: str,
    cnpj: str,
    price: str,
    report: str,
    composition: str,
    previous_report: str,
    result: RunResult,
    experiment_metadata: ExperimentMetadata,
) -> RunResult:
    all_raw = [str(i) for i in RawIndicator]
    extracted = {str(i.indicator) for i in result.final_output.indicators}
    missing_indicators = [
        r
        for r in all_raw
        if r not in extracted
        or next((i.value for i in result.final_output.indicators if str(i.indicator) == r), 0) == 0
    ]
    if len(missing_indicators) > 0:
        # reflection
        feedback = f"Extraia SOMENTE os seguintes indicadores do relatório: {missing_indicators}"
        inp_data = TEMPLATE_INPUT.format(
            name=name,
            cnpj=cnpj,
            price_str=price,
            report=report,
            composition=composition,
            previous_report=previous_report,
            feedback=feedback,
        )
        reflected_result = asyncio.run(
            Runner.run(agent, input=inp_data, max_turns=experiment_metadata.max_turns)
        )
        for i in reflected_result.final_output.indicators:
            if str(i.indicator) in missing_indicators:
                result.final_output.indicators = [
                    i_
                    for i_ in result.final_output.indicators
                    if str(i.indicator) != str(i_.indicator)
                ]
                result.final_output.indicators.append(i)

        result.context_wrapper.usage.requests += reflected_result.context_wrapper.usage.requests
        result.context_wrapper.usage.input_tokens += (
            reflected_result.context_wrapper.usage.input_tokens
        )
        result.context_wrapper.usage.output_tokens += (
            reflected_result.context_wrapper.usage.output_tokens
        )
        result.context_wrapper.usage.total_tokens += (
            reflected_result.context_wrapper.usage.total_tokens
        )

    return result


def run(experiment_metadata: ExperimentMetadata, n_times: int = 3):
    write_folder = f"{experiment_metadata.write_folder}/{experiment_metadata.model}/workflow_{experiment_metadata.reflection}"
    os.makedirs(write_folder, exist_ok=True)
    with open(f"""{write_folder}/experiment_metadata.json""", "w") as f:
        json.dump(experiment_metadata.model_dump(), f, indent=4)

    agent = init_agent(experiment_metadata=experiment_metadata)
    price_df = pd.read_csv(PRICE_FILE)
    for stock in STOCKS:
        name, cnpj, stock_id = stock.name, stock.cnpj, stock.stock_id
        price = float(price_df[price_df["Papel"] == stock_id].iloc[0]["Cotação"])
        price_str = f"{price:.2f}".replace(".", ",")

        for experiment_id in range(n_times):
            if os.path.exists(f"{write_folder}/{stock_id}_{experiment_id}.json"):
                continue
            print(stock, experiment_id)
            start = time.time()
            report = get_stock_report(cnpj=cnpj, date="2024-12-31")
            composition = get_stock_composition(cnpj=cnpj, date="2024-12-31")
            previous_report = get_stock_report(cnpj=cnpj, date="2024-09-30")
            result = analyse(
                agent=agent,
                name=name,
                cnpj=cnpj,
                price=price_str,
                report=report,
                composition=composition,
                previous_report=previous_report,
                experiment_metadata=experiment_metadata,
            )
            if experiment_metadata.reflection:
                result = guardrail(
                    agent=agent,
                    name=name,
                    cnpj=cnpj,
                    price=price_str,
                    report=report,
                    composition=composition,
                    previous_report=previous_report,
                    result=result,
                    experiment_metadata=experiment_metadata,
                )

            # fetch base fields from DB and compute all derived indicators arithmetically
            db_fields = get_db_fields(cnpj=cnpj, date="2024-12-31", prev_date="2024-09-30")
            total_shares = get_total_shares(cnpj=cnpj, date="2024-12-31")
            result.final_output = compute_indicators(
                raw=result.final_output,
                db_fields=db_fields,
                price=price,
                total_shares=total_shares,
            )
            end = time.time()

            save_results(
                write_folder=write_folder,
                stock_id=stock_id,
                result=result,
                elapsed_time=end - start,
                experiment_id=experiment_id,
            )
            time.sleep(40)
