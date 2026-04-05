import asyncio

from agents import Agent, ModelSettings, RunConfig, Runner, RunResult
from datetime import datetime
from src.experiments import Intensity, Model, StockInput, is_maritaca_model
from src.experiments.providers import get_run_config
from src.tools import code_interpreter
from src.financial_agents import get_agent
from src.financial_agents.financial_manager import (
    MANAGER_INSTRUCTIONS,
    FinanceOutput,
)

TEMPLATE_INPUT = """Empresa: {name} (CNPJ {cnpj})
Data: {date}
Cotação: {price_str}

{indicators}

{material_facts_report}
"""


def init_agent(model: Model = Model.GPT_5_MINI) -> Agent:
    if is_maritaca_model(model):
        model_settings = ModelSettings()
    else:
        from openai.types.shared import Reasoning

        model_settings = ModelSettings(
            reasoning=Reasoning(effort=Intensity.HIGH),
            verbosity=Intensity.MEDIUM,
        )

    return get_agent(
        name="financial_manager",
        instructions=MANAGER_INSTRUCTIONS,
        tools=[
            code_interpreter,
        ],
        servers=[],
        model=model,
        model_settings=model_settings,
        output_type=FinanceOutput,
    )


def analyse(
    agent: Agent,
    name: str,
    cnpj: str,
    price: str,
    analysis_date: datetime,
    indicators: str,
    max_turns: int,
    material_facts_report: str = "",
    run_config: RunConfig | None = None,
) -> RunResult:
    inp_data = TEMPLATE_INPUT.format(
        name=name,
        cnpj=cnpj,
        date=analysis_date.strftime("%Y-%m-%d"),
        price_str=price,
        indicators=indicators,
        material_facts_report=material_facts_report,
    )

    return asyncio.run(
        Runner.run(agent, input=inp_data, max_turns=max_turns, run_config=run_config)
    )


def run(
    stock: StockInput,
    stock_price: float,
    date: str | datetime,
    indicators: str,
    max_turns: int,
    material_facts_report: str = "",
    model: Model = Model.GPT_5_MINI,
):
    run_config = get_run_config(model)
    agent = init_agent(model)

    result = analyse(
        agent=agent,
        name=stock.name,
        cnpj=stock.cnpj,
        price=str(stock_price),
        analysis_date=date,
        indicators=indicators,
        max_turns=max_turns,
        material_facts_report=material_facts_report,
        run_config=run_config,
    )

    return result
