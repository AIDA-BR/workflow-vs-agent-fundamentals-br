"""Plotagem dos indicadores técnicos em gráficos para as variações 'imagem' e
'híbrido' do analista técnico.

Os indicadores plotados são exatamente os mesmos calculados em
src/tools/technical_indicators.py — só muda a modalidade de apresentação
(gráfico em vez de planilha). O PNG é salvo em disco (inspeção/paper) e também
retornado como data URL base64 para ser enviado ao modelo com visão.
"""

import base64
import os
from datetime import datetime

import matplotlib

matplotlib.use("Agg")  # backend sem display, seguro para execução headless
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402
import pandas as pd  # noqa: E402

from src.tools.technical_indicators import RSI_PERIOD  # noqa: E402


def _encode_png(path: str) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def plot_technical_charts(
    df: pd.DataFrame,
    stock_id: str,
    end_date: str | datetime,
    out_dir: str,
    plot_tail: int = 126,
) -> tuple[list[str], list[str]]:
    """Gera o gráfico técnico de uma ação e retorna (caminhos_png, data_urls).

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame já com indicadores (saída de ``compute_indicators``).
    stock_id : str
        Código da ação (usado no título e no nome do arquivo).
    end_date : str | datetime
        Data de referência (usada no nome do arquivo).
    out_dir : str
        Diretório onde o PNG será salvo (criado se não existir).
    plot_tail : int
        Número de pregões mais recentes a exibir (~6 meses). Os indicadores são
        calculados sobre o histórico completo; apenas a janela visível é
        recortada para legibilidade.

    Returns
    -------
    tuple[list[str], list[str]]
        Lista de caminhos dos PNGs e lista de data URLs base64 correspondentes.
    """
    if df.empty:
        return [], []

    if isinstance(end_date, datetime):
        end_date = end_date.strftime("%Y-%m-%d")
    os.makedirs(out_dir, exist_ok=True)

    view = df.tail(plot_tail).copy()
    dates = view["date"]

    fig, (ax_price, ax_vol, ax_macd, ax_rsi) = plt.subplots(
        4,
        1,
        figsize=(14, 12),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1, 1.2, 1.2]},
    )
    fig.suptitle(f"Análise Técnica — {stock_id} (até {end_date})", fontsize=15, fontweight="bold")

    # --- Painel 1: preço, médias móveis e Bandas de Bollinger ---
    ax_price.plot(dates, view["close"], color="black", linewidth=1.4, label="Fechamento")
    for col, color in [("MM20", "tab:blue"), ("MM50", "tab:orange"), ("MM200", "tab:red")]:
        if col in view:
            ax_price.plot(dates, view[col], linewidth=1.0, label=col, color=color)
    for col, color in [("EMA9", "tab:green"), ("EMA21", "tab:purple")]:
        if col in view:
            ax_price.plot(dates, view[col], linewidth=0.9, linestyle="--", label=col, color=color)
    if {"BB_upper", "BB_lower"}.issubset(view.columns):
        ax_price.plot(dates, view["BB_upper"], color="gray", linewidth=0.7, alpha=0.7)
        ax_price.plot(dates, view["BB_lower"], color="gray", linewidth=0.7, alpha=0.7)
        ax_price.fill_between(
            dates,
            view["BB_lower"],
            view["BB_upper"],
            color="gray",
            alpha=0.10,
            label="Bollinger (20, 2σ)",
        )
    ax_price.set_ylabel("Preço (R$)")
    ax_price.legend(loc="upper left", fontsize=8, ncol=3)
    ax_price.grid(True, alpha=0.3)

    # --- Painel 2: volume ---
    ax_vol.bar(dates, view["volume"], color="tab:blue", alpha=0.5, width=1.0)
    ax_vol.set_ylabel("Volume")
    ax_vol.grid(True, alpha=0.3)

    # --- Painel 3: MACD ---
    if {"MACD", "MACD_signal", "MACD_hist"}.issubset(view.columns):
        ax_macd.plot(dates, view["MACD"], color="tab:blue", linewidth=1.0, label="MACD")
        ax_macd.plot(dates, view["MACD_signal"], color="tab:orange", linewidth=1.0, label="Sinal")
        hist_colors = ["tab:green" if v >= 0 else "tab:red" for v in view["MACD_hist"]]
        ax_macd.bar(dates, view["MACD_hist"], color=hist_colors, alpha=0.5, width=1.0)
        ax_macd.axhline(0, color="black", linewidth=0.6)
        ax_macd.set_ylabel("MACD")
        ax_macd.legend(loc="upper left", fontsize=8)
        ax_macd.grid(True, alpha=0.3)

    # --- Painel 4: RSI ---
    if "RSI14" in view:
        ax_rsi.plot(
            dates, view["RSI14"], color="tab:purple", linewidth=1.0, label=f"RSI{RSI_PERIOD}"
        )
        ax_rsi.axhline(70, color="tab:red", linewidth=0.7, linestyle="--")
        ax_rsi.axhline(30, color="tab:green", linewidth=0.7, linestyle="--")
        ax_rsi.set_ylim(0, 100)
        ax_rsi.set_ylabel("RSI")
        ax_rsi.legend(loc="upper left", fontsize=8)
        ax_rsi.grid(True, alpha=0.3)

    ax_rsi.xaxis.set_major_locator(mdates.MonthLocator())
    ax_rsi.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate()
    fig.tight_layout(rect=(0, 0, 1, 0.98))

    path = os.path.join(out_dir, f"{end_date}_technical.png")
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)

    return [path], [_encode_png(path)]
