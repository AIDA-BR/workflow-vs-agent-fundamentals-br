"""Orquestração do analista técnico e suas três variações de modalidade.

As variações compartilham exatamente os mesmos indicadores (calculados em
src/tools/technical_indicators.py); o que muda é apenas COMO eles são
apresentados ao modelo:

- PLANILHA: tabela textual + interpretador Python.
- IMAGEM:   gráficos plotados (entrada multimodal / visão).
- HIBRIDO:  planilha e gráficos simultaneamente.

Objetivo: comparar de forma controlada qual modalidade produz o melhor resultado
de trading a jusante (via gestor).
"""

from datetime import datetime

from agents import Agent, ModelSettings, RunConfig, Runner, RunResult

from src.experiments import Intensity, Model, StockInput, TechnicalVariant, is_maritaca_model
from src.experiments.providers import get_run_config
from src.financial_agents import get_agent
from src.financial_agents.technical_analyst import (
    TECHNICAL_ANALYST_INSTRUCTIONS,
    TechnicalAnalysisOutput,
)
from src.tools import code_interpreter
from src.tools.technical_charts import plot_technical_charts
from src.tools.technical_indicators import (
    compute_indicators,
    get_price_history,
    indicators_to_spreadsheet,
)

_HEADER = "Empresa: {name} ({stock_id})\nData de referência: {date}\n"

_PLANILHA_INTRO = (
    "Abaixo está a planilha com o histórico diário de preço/volume e os "
    "indicadores técnicos já calculados (uma linha por pregão):\n\n{spreadsheet}"
)

_IMAGEM_INTRO = (
    "Em anexo estão os gráficos com os indicadores técnicos plotados "
    "(preço com médias móveis e Bandas de Bollinger, volume, MACD e RSI). "
    "Analise os padrões visuais e produza o relatório técnico."
)


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
        name="technical_analyst",
        instructions=TECHNICAL_ANALYST_INSTRUCTIONS,
        tools=[code_interpreter],
        servers=[],
        model=model,
        model_settings=model_settings,
        output_type=TechnicalAnalysisOutput,
    )


def _build_input(
    header: str,
    variant: TechnicalVariant,
    spreadsheet: str,
    image_urls: list[str],
) -> str | list:
    """Monta a entrada do agente conforme a modalidade.

    Para PLANILHA a entrada é um texto simples; para IMAGEM/HIBRIDO é uma
    mensagem multimodal (formato Responses API) com itens ``input_image``.
    """
    if variant == TechnicalVariant.PLANILHA:
        return header + "\n" + _PLANILHA_INTRO.format(spreadsheet=spreadsheet)

    content: list[dict] = []
    if variant == TechnicalVariant.HIBRIDO:
        text = (
            header + "\n" + _PLANILHA_INTRO.format(spreadsheet=spreadsheet) + "\n\n" + _IMAGEM_INTRO
        )
    else:  # IMAGEM
        text = header + "\n" + _IMAGEM_INTRO

    content.append({"type": "input_text", "text": text})
    for url in image_urls:
        content.append({"type": "input_image", "image_url": url})

    return [{"role": "user", "content": content}]


async def run(
    stock: StockInput,
    end_date: str | datetime,
    variant: TechnicalVariant,
    charts_dir: str,
    model: Model = Model.GPT_5_MINI,
    max_turns: int = 15,
    lookback_days: int = 365,
) -> tuple[RunResult, list[str]]:
    """Roda o analista técnico para uma ação em uma data de decisão.

    Returns
    -------
    tuple[RunResult, list[str]]
        O resultado do agente (com contagem de tokens via context_wrapper.usage)
        e a lista de caminhos dos PNGs gerados (vazia na variação planilha).
    """
    if isinstance(end_date, str):
        end_date = datetime.fromisoformat(end_date)

    df = compute_indicators(get_price_history(stock.stock_id, end_date, lookback_days))

    spreadsheet = ""
    image_urls: list[str] = []
    png_paths: list[str] = []

    if variant in (TechnicalVariant.PLANILHA, TechnicalVariant.HIBRIDO):
        spreadsheet = indicators_to_spreadsheet(df)
    if variant in (TechnicalVariant.IMAGEM, TechnicalVariant.HIBRIDO):
        png_paths, image_urls = plot_technical_charts(
            df, stock.stock_id, end_date, out_dir=charts_dir
        )

    header = _HEADER.format(
        name=stock.name, stock_id=stock.stock_id, date=end_date.strftime("%Y-%m-%d")
    )
    inp = _build_input(header, variant, spreadsheet, image_urls)

    run_config: RunConfig = get_run_config(model)
    agent = init_agent(model)
    result = await Runner.run(agent, input=inp, max_turns=max_turns, run_config=run_config)
    return result, png_paths


def format_technical_report(output: dict) -> str:
    """Formata o output estruturado do analista técnico em texto para o gestor."""
    supports = ", ".join(str(s) for s in output.get("support_levels", [])) or "N/A"
    resistances = ", ".join(str(r) for r in output.get("resistance_levels", [])) or "N/A"
    readings = "\n".join(
        f"- {r['indicator']}: {r['reading']} — {r['interpretation']}"
        for r in output.get("indicator_readings", [])
    )
    return (
        "## Relatório de Análise Técnica\n\n"
        f"Sinal: {output.get('signal', 'N/A')}\n"
        f"Suportes: {supports}\n"
        f"Resistências: {resistances}\n\n"
        f"{output.get('report', '')}\n\n"
        f"Leitura por indicador:\n{readings}"
    )
