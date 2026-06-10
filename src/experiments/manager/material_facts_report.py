import time

from agents import ModelSettings, RunResult, Runner
from src.experiments.providers import get_run_config
from datetime import datetime, timedelta

from src.experiments import Model, StockInput
from src.experiments.utils import AgentResult, LLMUsage
from src.financial_agents import get_agent
from src.financial_agents.material_facts_summarizer import (
    MONTHLY_SUMMARIZER_INSTRUCTIONS,
    SIX_MONTH_SUMMARIZER_INSTRUCTIONS,
    MonthlySummary,
    SixMonthSummary,
)
from src.tools.material_facts import fetch_material_facts, fetch_material_facts_from_ipe


class _UsageAccumulator:
    """Acumula tokens e steps de múltiplas chamadas LLM (resumos mensais + consolidação).

    O analista de fatos relevantes faz N chamadas ao LLM por data de decisão.
    Para salvar no mesmo padrão JSON do gestor (usage/steps/time/output), agregamos
    o uso de todas as chamadas efetivamente realizadas. Chamadas servidas pelo cache
    não contam (custo marginal por data).
    """

    def __init__(self) -> None:
        self.requests = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.steps: list = []

    def add(self, result: RunResult) -> None:
        usage = result.context_wrapper.usage
        self.requests += usage.requests
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.total_tokens += usage.total_tokens
        self.steps.extend(item.to_input_item() for item in result.new_items)


async def get_monthly_summary(
    stock: StockInput,
    year: int,
    month: int,
    model: Model,
    cache: dict,
    raw_facts_cache: dict | None = None,
    usage_acc: "_UsageAccumulator | None" = None,
) -> MonthlySummary:
    cache_key = (stock.stock_id, year, month)
    if cache_key in cache:
        return cache[cache_key]

    if raw_facts_cache is not None:
        news = raw_facts_cache.get(f"{stock.stock_id}|{year}|{month}", [])
    else:
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
        model=model,
        model_settings=ModelSettings(),
        output_type=MonthlySummary,
    )

    run_config = get_run_config(model)
    run_result = await Runner.run(agent, input=inp, max_turns=5, run_config=run_config)
    if usage_acc is not None:
        usage_acc.add(run_result)
    summary: MonthlySummary = run_result.final_output
    cache[cache_key] = summary
    return summary


async def get_six_month_summary(
    stock: StockInput,
    analysis_date: datetime,
    model: Model,
    cache: dict,
    raw_facts_cache: dict | None = None,
    usage_acc: "_UsageAccumulator | None" = None,
) -> SixMonthSummary:
    # Compute the 6 calendar months ending at the month before analysis_date
    months = []
    ref = analysis_date.replace(day=1) - timedelta(days=1)  # last day of previous month
    for _ in range(6):
        months.append((ref.year, ref.month))
        ref = ref.replace(day=1) - timedelta(days=1)
    months.reverse()

    monthly_summaries = [
        await get_monthly_summary(stock, y, m, model, cache, raw_facts_cache, usage_acc)
        for y, m in months
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
        model=model,
        model_settings=ModelSettings(),
        output_type=SixMonthSummary,
    )

    run_config = get_run_config(model)
    run_result = await Runner.run(agent, input=inp, max_turns=5, run_config=run_config)
    if usage_acc is not None:
        usage_acc.add(run_result)
    return run_result.final_output


async def get_six_month_result(
    stock: StockInput,
    analysis_date: datetime,
    model: Model,
    cache: dict,
    raw_facts_cache: dict | None = None,
) -> tuple[SixMonthSummary, AgentResult]:
    """Como get_six_month_summary, mas também retorna o resultado no padrão JSON.

    Agrega tokens/steps de todas as chamadas LLM realizadas (resumos mensais +
    consolidação) num dicionário compatível com ``AgentResult`` (usage/steps/
    time/output), permitindo salvar o analista de fatos relevantes no mesmo
    formato JSON do gestor e do analista fundamentalista.
    """
    usage_acc = _UsageAccumulator()
    start_time = time.time()
    summary = await get_six_month_summary(
        stock, analysis_date, model, cache, raw_facts_cache, usage_acc
    )
    elapsed_time = time.time() - start_time

    agent_result = AgentResult(
        usage=LLMUsage(
            requests=usage_acc.requests,
            input_tokens=usage_acc.input_tokens,
            output_tokens=usage_acc.output_tokens,
            total_tokens=usage_acc.total_tokens,
        ),
        steps=usage_acc.steps,
        time=elapsed_time,
        output=summary.model_dump(),
    )
    return summary, agent_result


def format_six_month_report(summary: SixMonthSummary) -> str:
    key_events = "\n".join(f"- {event}" for event in summary.key_events)
    return (
        f"## Relatório de Fatos Relevantes (últimos 6 meses)\n\n"
        f"Período: {summary.period}\n\n"
        f"{summary.summary}\n\n"
        f"Eventos-chave:\n{key_events}"
    )
