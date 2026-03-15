import asyncio
import json
import os
import pandas as pd
import time

from agents import Agent, ModelSettings, Runner, RunResult
from openai.types.shared import Reasoning

from src.experiments import ExperimentMetadata
from src.experiments.fundamental_analysis.config import STOCKS
from src.experiments.utils import save_results
from src.financial_agents import get_agent
from src.financial_agents.financial_analyst import (
    FINANCIAL_ANALYST_INSTRUCTION,
    Indicator,
    IndicatorOutput,
)
from src.settings import PRICE_FILE
from src.tools import code_interpreter, cvm_base_query_tool, cvm_composition_query_tool

TEMPLATE_INPUT = """Fazer análise fundamentalista da empresa {name} (CNPJ {cnpj}) em Dezembro de 2024 com cotação a {price_str} reais.

Feedback: {feedback}"""


def init_agent(experiment_metadata: ExperimentMetadata) -> Agent:
    model_settings = ModelSettings(tool_choice="required")
    if experiment_metadata.reasoning is not None:
        reasoning = Reasoning(effort=experiment_metadata.reasoning)
        model_settings = ModelSettings(
            reasoning=reasoning,
            verbosity=experiment_metadata.verbosity,
        )

    agent = get_agent(
        name="financial_analyst",
        instructions=FINANCIAL_ANALYST_INSTRUCTION,
        tools=[
            code_interpreter,
            cvm_base_query_tool,
            cvm_composition_query_tool,
        ],
        servers=[],
        model=experiment_metadata.model,
        model_settings=model_settings,
        output_type=IndicatorOutput,
    )
    return agent


def analyse(
    agent: Agent,
    name: str,
    cnpj: str,
    price: str,
    experiment_metadata: ExperimentMetadata,
) -> RunResult:
    feedback = "Compute todos os indicadores fundamentalistas disponíveis"

    inp_data = TEMPLATE_INPUT.format(name=name, cnpj=cnpj, price_str=price, feedback=feedback)
    # agent
    return asyncio.run(Runner.run(agent, input=inp_data, max_turns=experiment_metadata.max_turns))


def guardrail(
    agent: Agent,
    name: str,
    cnpj: str,
    price: str,
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
        inp_data = TEMPLATE_INPUT.format(name=name, cnpj=cnpj, price_str=price, feedback=feedback)
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
    """
    Runs the experiment on all the stocks in the PRICE_FILE CSV file.

    Parameters:
    experiment_metadata (ExperimentMetadata): The experiment metadata object.
    n_times (int): The number of times to run the experiment. Defaults to 3.

    Returns:
    None
    """
    write_folder = f"{experiment_metadata.write_folder}/{experiment_metadata.model}/agent_{experiment_metadata.reflection}"
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
            result = analyse(
                agent=agent,
                name=name,
                cnpj=cnpj,
                price=price_str,
                experiment_metadata=experiment_metadata,
            )
            if experiment_metadata.reflection:
                result = guardrail(
                    agent=agent,
                    name=name,
                    cnpj=cnpj,
                    price=price_str,
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
