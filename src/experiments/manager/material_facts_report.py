import asyncio

from agents import ModelSettings, Runner
from datetime import datetime, timedelta

from src.experiments import ExperimentMetadata, StockInput
from src.financial_agents import get_agent
from src.financial_agents.material_facts_summarizer import (
    MONTHLY_SUMMARIZER_INSTRUCTIONS,
    SIX_MONTH_SUMMARIZER_INSTRUCTIONS,
    MonthlySummary,
    SixMonthSummary,
)
from src.tools.material_facts import fetch_material_facts, fetch_material_facts_from_ipe


def get_monthly_summary(
    stock: StockInput,
    year: int,
    month: int,
    experiment_metadata: ExperimentMetadata,
    cache: dict,
) -> MonthlySummary:
    cache_key = (stock.stock_id, year, month)
    if cache_key in cache:
        return cache[cache_key]

    news = fetch_material_facts_from_ipe(
        cnpj=stock.cnpj, ticker=stock.stock_id, year=year, month=month
    )
    if not news:
        news = fetch_material_facts(ticker=stock.stock_id, year=year, month=month)

    if not news:
        result = MonthlySummary(
            ticker=stock.stock_id,
            year=year,
            month=month,
            summary="Sem comunicados divulgados neste mês.",
            has_material_events=False,
        )
        cache[cache_key] = result
        return result

    news_text = "\n\n".join(
        f"{i + 1}. [{n['data_hora']}] {n['headline']}\n{n['conteudo']}" for i, n in enumerate(news)
    )

    inp = (
        f"Empresa: {stock.name} ({stock.stock_id})\n"
        f"Mês de referência: {year}-{month:02d}\n\n"
        f"Comunicados:\n{news_text}"
    )

    agent = get_agent(
        name="monthly_summarizer",
        instructions=MONTHLY_SUMMARIZER_INSTRUCTIONS,
        tools=[],
        servers=[],
        model=experiment_metadata.model,
        model_settings=ModelSettings(),
        output_type=MonthlySummary,
    )

    run_result = asyncio.run(Runner.run(agent, input=inp, max_turns=5))
    summary: MonthlySummary = run_result.final_output
    cache[cache_key] = summary
    return summary


def get_six_month_summary(
    stock: StockInput,
    analysis_date: datetime,
    experiment_metadata: ExperimentMetadata,
    cache: dict,
) -> SixMonthSummary:
    # Compute the 6 calendar months ending at the month before analysis_date
    months = []
    ref = analysis_date.replace(day=1) - timedelta(days=1)  # last day of previous month
    for _ in range(6):
        months.append((ref.year, ref.month))
        ref = ref.replace(day=1) - timedelta(days=1)
    months.reverse()

    monthly_summaries = [
        get_monthly_summary(stock, y, m, experiment_metadata, cache) for y, m in months
    ]

    start_ym = f"{months[0][0]}-{months[0][1]:02d}"
    end_ym = f"{months[-1][0]}-{months[-1][1]:02d}"
    period = f"{start_ym} a {end_ym}"

    summaries_text = "\n\n".join(
        f"Resumo de {s.year}-{s.month:02d} (has_material_events: {s.has_material_events}):\n{s.summary}"
        for s in monthly_summaries
    )

    inp = f"Empresa: {stock.name} ({stock.stock_id})\nPeríodo: {period}\n\n{summaries_text}"

    agent = get_agent(
        name="six_month_summarizer",
        instructions=SIX_MONTH_SUMMARIZER_INSTRUCTIONS,
        tools=[],
        servers=[],
        model=experiment_metadata.model,
        model_settings=ModelSettings(),
        output_type=SixMonthSummary,
    )

    run_result = asyncio.run(Runner.run(agent, input=inp, max_turns=5))
    return run_result.final_output


def format_six_month_report(summary: SixMonthSummary) -> str:
    key_events = "\n".join(f"- {event}" for event in summary.key_events)
    return (
        f"## Relatório de Fatos Relevantes (últimos 6 meses)\n\n"
        f"Período: {summary.period}\n\n"
        f"{summary.summary}\n\n"
        f"Eventos-chave:\n{key_events}"
    )
