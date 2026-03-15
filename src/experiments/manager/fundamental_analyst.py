import asyncio

from agents import Agent, ModelSettings, Runner, RunResult
from datetime import datetime, timedelta
from src.db import get_stock_report, get_stock_composition
from src.experiments import ExperimentMetadata, StockInput
from openai.types.shared import Reasoning
from src.tools import code_interpreter
from src.financial_agents import get_agent
from src.financial_agents.financial_analyst import (
    FINANCIAL_ANALYST_INSTRUCTION,
    IndicatorOutput,
    Indicator,
)

TEMPLATE_INPUT = """Fazer análise fundamentalista da empresa {name} (CNPJ {cnpj}) em {date} com cotação a {price_str} reais.

# Relatório DFP/ITR de {date}
{report}

# Composição de ativos de {date}
{composition}

# Relatório DFP/ITR do Trimestre Anterior ({previous_date})
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


def analyse(
    agent: Agent,
    name: str,
    cnpj: str,
    price: str,
    analysis_date: datetime,
    report: str,
    composition: str,
    previous_report: str,
    experiment_metadata: ExperimentMetadata,
) -> RunResult:
    feedback = "Compute todos os indicadores fundamentalistas disponíveis"

    inp_data = TEMPLATE_INPUT.format(
        name=name,
        cnpj=cnpj,
        date=analysis_date.strftime("%Y-%m-%d"),
        previous_date=(analysis_date.replace(day=1) - timedelta(days=90)).strftime("%Y-%m"),
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
    analysis_date: datetime,
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
            date=analysis_date.strftime("%Y-%m-%d"),
            previous_date=(analysis_date.replace(day=1) - timedelta(days=90)).strftime("%Y-%m"),
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


def run(
    stock: StockInput,
    stock_price: float,
    date: str | datetime,
    experiment_metadata: ExperimentMetadata,
):
    agent = init_agent(experiment_metadata=experiment_metadata)

    # Get last quarter reports of the stock (previous 3 months)
    report = get_stock_report(cnpj=stock.cnpj, date=date)
    composition = get_stock_composition(cnpj=stock.cnpj, date=date)

    # Get previous reports of the stock (previous 6 months)
    previous_date = date.replace(day=1) - timedelta(days=90)
    previous_report = get_stock_report(cnpj=stock.cnpj, date=previous_date)
    composition = get_stock_composition(cnpj=stock.cnpj, date=previous_date)

    result = analyse(
        agent=agent,
        name=stock.name,
        cnpj=stock.cnpj,
        price=str(stock_price),
        analysis_date=date,
        report=report,
        composition=composition,
        previous_report=previous_report,
        experiment_metadata=experiment_metadata,
    )
    if experiment_metadata.reflection:
        result = guardrail(
            agent=agent,
            name=stock.name,
            cnpj=stock.cnpj,
            price=str(stock_price),
            analysis_date=date,
            report=report,
            composition=composition,
            previous_report=previous_report,
            result=result,
            experiment_metadata=experiment_metadata,
        )

    return result
