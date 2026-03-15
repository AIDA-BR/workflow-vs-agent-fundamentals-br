import asyncio
import json
import os
import pandas as pd
import time

from agents import Agent, ModelSettings, Runner, RunResult
from openai.types.shared import Reasoning

from src.db.base_query import run_sql_query
from src.experiments import ExperimentMetadata
from src.experiments.fundamental_analysis.config import STOCKS
from src.experiments.utils import save_results
from src.financial_agents import get_agent
from src.financial_agents.financial_analyst import (
    FINANCIAL_ANALYST_INSTRUCTION,
    Indicator,
    IndicatorOutput,
)
from src.settings import DB_PATH, PRICE_FILE
from src.tools import code_interpreter

TEMPLATE_INPUT = """Fazer análise fundamentalista da empresa {name} (CNPJ {cnpj}) em Dezembro de 2024 com cotação a {price_str} reais.

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
        tools=[
            code_interpreter,
        ],
        servers=[],
        model=experiment_metadata.model,
        model_settings=model_settings,
        output_type=IndicatorOutput,
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
    feedback = "Compute todos os indicadores fundamentalistas disponíveis"

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
    all_indicators = [str(i) for i in Indicator]
    missing_indicators = [
        str(i.indicator)
        for i in result.final_output.indicators
        if str(i.indicator) not in all_indicators or i.value == 0
    ]
    if len(missing_indicators) > 0:
        # reflection
        feedback = (
            f"Compute SOMENTE os seguintes indicadores fundamentalistas: {missing_indicators}"
        )
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
            end = time.time()

            save_results(
                write_folder=write_folder,
                stock_id=stock_id,
                result=result,
                elapsed_time=end - start,
                experiment_id=experiment_id,
            )
            time.sleep(40)
