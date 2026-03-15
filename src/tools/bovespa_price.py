from agents import function_tool

from src.db.base_query import QueryInput, run_sql_query
from src.settings import PRICE_DB_PATH as DB_PATH


@function_tool
def bovespa_stock_price_query_tool(inp: QueryInput) -> dict:
    """Consultar um Banco de Dados SQL de Preços de Ações listados no Mercado de Ações Brasileiro com o seguinte esquema:

    CREATE TABLE IF NOT EXISTS COTAHIST (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        CNPJ TEXT NOT NULL, # CNPJ da empresa (Formato 00.000.000/0000-00)
        DATA_DO_PREGAO DATETIME NOT NULL, # Data do pregão
        NOME_DA_EMPRESA TEXT NOT NULL, # Nome da empresa
        CODIGO_DE_NEGOCIACAO TEXT NOT NULL, # Código de Negociação da ação
        ESPECIFICACAO_DO_PAPEL TEXT NOT NULL, # Especificação do papel
        MOEDA_DE_REFERENCIA TEXT NOT NULL, # Moeda
        PRECO_DE_ABERTURA FLOAT NOT NULL, # Preço de Abertura na data
        PRECO_MAXIMO FLOAT NOT NULL, # Preço Máximo no dia
        PRECO_MINIMO FLOAT NOT NULL, # Preço Minimo no dia
        PRECO_MEDIO FLOAT NOT NULL, # Preço Médio no dia
        PRECO_ULTIMO_NEGOCIO FLOAT NOT NULL, # Preço do ultimo negócio
        PRECO_MELHOR_OFERTA_DE_COMPRA FLOAT NOT NULL, # Preço da melhor oferta de compra
        NUMERO_DE_NEGOCIOS INT NOT NULL, # Número de negócios feitos no dia
        QUANTIDADE_NEGOCIADA INT NOT NULL, # Quantidade de papéis negociados no dia
        VOLUME_TOTAL_NEGOCIADO INT NOT NULL # Volume total negociado no dia
    )
    """
    return run_sql_query(inp, db_path=DB_PATH)
