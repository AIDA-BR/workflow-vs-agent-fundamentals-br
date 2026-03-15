__author__ = "thiagocastroferreira"

from datetime import datetime, timedelta

from src.db.base_query import ResponseFormat, run_sql_query
from src.settings import DB_PATH as CVM_DATABASE_PATH
from src.settings import PRICE_DB_PATH as PRICE_DATABASE_PATH


def _get_month_range(date: datetime) -> tuple[str, str]:
    start_date = date.replace(day=1)
    end_date = start_date + timedelta(days=32)

    start_date = start_date.strftime("%Y-%m-%d")
    end_date = end_date.replace(day=1).strftime("%Y-%m-%d")
    return start_date, end_date


def get_stock_report(cnpj: str, date: datetime) -> str:
    start_date, end_date = _get_month_range(date)

    query = f"""
    SELECT ACCOUNT_NUMBER, ACCOUNT_NAME, ACCOUNT_VALUE, VERSION, EXERC_ORDER, ANALYSIS_START_PERIOD_DATE, ANALYSIS_END_PERIOD_DATE
    FROM DFP_ITR_CVM
    WHERE CNPJ = '{cnpj}' AND REPORT_DATE >= '{start_date}' AND REPORT_DATE < '{end_date}'
    ORDER BY ACCOUNT_NUMBER;"""

    result = run_sql_query(inp={"sql_query": query}, db_path=CVM_DATABASE_PATH)
    return result.get("report", "")


def get_stock_composition(cnpj: str, date: datetime) -> str:
    start_date, end_date = _get_month_range(date)

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
    WHERE CNPJ = '{cnpj}' AND REPORT_DATE >= '{start_date}' AND REPORT_DATE < '{end_date}';"""

    result = run_sql_query(inp={"sql_query": query}, db_path=CVM_DATABASE_PATH)
    return result.get("report", "")


def get_stock_daily_info(
    stock_id: str,
    date: str | datetime,
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """
    Returns a string containing daily information about a given stock.

    Args:
        stock_id (str): The ID of the stock to query.
        date (str): The date to query in the format 'YYYY-MM-DD'.

    Returns:
        str: A string containing the daily information about the given stock.
    """
    if isinstance(date, datetime):
        date = date.strftime("%Y-%m-%d")

    query = f"""
    SELECT
        CNPJ,
        DATA_DO_PREGAO,
        NOME_DA_EMPRESA,
        CODIGO_DE_NEGOCIACAO,
        ESPECIFICACAO_DO_PAPEL,
        MOEDA_DE_REFERENCIA,
        PRECO_DE_ABERTURA,
        PRECO_MAXIMO,
        PRECO_MINIMO,
        PRECO_MEDIO,
        PRECO_ULTIMO_NEGOCIO,
        PRECO_MELHOR_OFERTA_DE_COMPRA,
        NUMERO_DE_NEGOCIOS,
        QUANTIDADE_NEGOCIADA,
        VOLUME_TOTAL_NEGOCIADO
    FROM COTAHIST
    WHERE CODIGO_DE_NEGOCIACAO = '{stock_id}' AND DATA_DO_PREGAO = '{date}';"""

    result = run_sql_query(
        inp={"sql_query": query},
        db_path=PRICE_DATABASE_PATH,
        response_format=response_format,
    )
    return result.get("report", "")
