"""Cálculo determinístico de indicadores de análise técnica.

Os indicadores são calculados uma única vez, de forma reprodutível (pandas puro),
e alimentam as três variações do analista técnico (planilha / imagem / híbrido).
Assim, apenas a *modalidade* de apresentação varia entre as variações — os números
são exatamente os mesmos —, garantindo uma comparação controlada para o paper.

Fonte dos preços: tabela COTAHIST em prices.db (mesma usada por
src/db/__init__.py e src/tools/bovespa_price.py). O preço de fechamento usado é
PRECO_ULTIMO_NEGOCIO e o volume é VOLUME_TOTAL_NEGOCIADO.
"""

from datetime import datetime, timedelta

import pandas as pd

from src.db.base_query import ResponseFormat, run_sql_query
from src.settings import PRICE_DB_PATH

# Períodos padrão dos indicadores.
MM_PERIODS = (20, 50, 200)
EMA_PERIODS = (9, 21)
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
BOLLINGER_PERIOD, BOLLINGER_STD = 20, 2
RSI_PERIOD = 14


def get_price_history(
    stock_id: str,
    end_date: str | datetime,
    lookback_days: int = 365,
) -> pd.DataFrame:
    """Retorna o histórico diário de preços de uma ação até ``end_date``.

    Parameters
    ----------
    stock_id : str
        Código de negociação da ação (ex.: "PETR4").
    end_date : str | datetime
        Data final (inclusive) da janela.
    lookback_days : int
        Tamanho da janela em dias corridos. O padrão de ~1 ano garante candles
        suficientes para a MM200.

    Returns
    -------
    pd.DataFrame
        OHLCV diário ordenado por data, com coluna ``date`` (datetime) e as
        colunas ``open``, ``high``, ``low``, ``close``, ``volume`` e
        ``quantity``.
    """
    if isinstance(end_date, datetime):
        end_date = end_date.strftime("%Y-%m-%d")
    start_date = (datetime.fromisoformat(end_date) - timedelta(days=lookback_days)).strftime(
        "%Y-%m-%d"
    )

    query = f"""
    SELECT
        DATA_DO_PREGAO,
        PRECO_DE_ABERTURA,
        PRECO_MAXIMO,
        PRECO_MINIMO,
        PRECO_ULTIMO_NEGOCIO,
        VOLUME_TOTAL_NEGOCIADO,
        QUANTIDADE_NEGOCIADA
    FROM COTAHIST
    WHERE CODIGO_DE_NEGOCIACAO = '{stock_id}'
        AND DATA_DO_PREGAO >= '{start_date}'
        AND DATA_DO_PREGAO <= '{end_date}'
    ORDER BY DATA_DO_PREGAO ASC;"""

    result = run_sql_query(
        inp={"sql_query": query},
        db_path=PRICE_DB_PATH,
        response_format=ResponseFormat.DICT,
    )
    rows = result.get("report", [])
    if not isinstance(rows, list) or len(rows) == 0:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "quantity"])

    df = pd.DataFrame(rows).rename(
        columns={
            "DATA_DO_PREGAO": "date",
            "PRECO_DE_ABERTURA": "open",
            "PRECO_MAXIMO": "high",
            "PRECO_MINIMO": "low",
            "PRECO_ULTIMO_NEGOCIO": "close",
            "VOLUME_TOTAL_NEGOCIADO": "volume",
            "QUANTIDADE_NEGOCIADA": "quantity",
        }
    )
    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "high", "low", "close", "volume", "quantity"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)


def _rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """RSI de Wilder (média móvel exponencial dos ganhos/perdas)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona ao DataFrame as colunas de indicadores técnicos.

    Indicadores: médias móveis simples (MM20/50/200), médias móveis exponenciais
    (EMA9/21), MACD (12, 26) com linha de sinal (9) e histograma, Bandas de
    Bollinger (20, 2 desvios) e RSI (14). O volume já vem do histórico.
    """
    if df.empty:
        return df

    out = df.copy()
    close = out["close"]

    for p in MM_PERIODS:
        out[f"MM{p}"] = close.rolling(window=p, min_periods=p).mean()
    for p in EMA_PERIODS:
        out[f"EMA{p}"] = close.ewm(span=p, adjust=False).mean()

    ema_fast = close.ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow = close.ewm(span=MACD_SLOW, adjust=False).mean()
    out["MACD"] = ema_fast - ema_slow
    out["MACD_signal"] = out["MACD"].ewm(span=MACD_SIGNAL, adjust=False).mean()
    out["MACD_hist"] = out["MACD"] - out["MACD_signal"]

    bb_mid = close.rolling(window=BOLLINGER_PERIOD, min_periods=BOLLINGER_PERIOD).mean()
    bb_std = close.rolling(window=BOLLINGER_PERIOD, min_periods=BOLLINGER_PERIOD).std()
    out["BB_mid"] = bb_mid
    out["BB_upper"] = bb_mid + BOLLINGER_STD * bb_std
    out["BB_lower"] = bb_mid - BOLLINGER_STD * bb_std

    out["RSI14"] = _rsi(close, RSI_PERIOD)
    return out


# Colunas exibidas na planilha entregue ao analista (ordem amigável).
_SPREADSHEET_COLUMNS = [
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "MM20",
    "MM50",
    "MM200",
    "EMA9",
    "EMA21",
    "MACD",
    "MACD_signal",
    "MACD_hist",
    "BB_lower",
    "BB_mid",
    "BB_upper",
    "RSI14",
]


def indicators_to_spreadsheet(df: pd.DataFrame, tail: int = 60) -> str:
    """Formata as últimas ``tail`` linhas como planilha textual (to_string).

    Segue o mesmo estilo da planilha de indicadores fundamentalistas entregue ao
    gestor em main_workflow.py.
    """
    if df.empty:
        return "Sem dados de preço disponíveis para o período."

    cols = [c for c in _SPREADSHEET_COLUMNS if c in df.columns]
    view = df[cols].tail(tail).copy()
    view["date"] = view["date"].dt.strftime("%Y-%m-%d")
    return view.round(4).to_string(index=False)
