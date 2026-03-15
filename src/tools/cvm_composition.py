from agents import function_tool

from src.db.base_query import QueryInput, run_sql_query
from src.settings import DB_PATH


@function_tool
def cvm_composition_query_tool(inp: QueryInput) -> dict:
    """Consultar um Banco de Dados SQL com o relatório de composição de ações das empresas do Mercado de Ações Brasileiro. Esquema:

    CREATE TABLE IF NOT EXISTS CVM_SHARE_COMPOSITION (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        CNPJ TEXT NOT NULL, # CNPJ da empresa (Formato 00.000.000/0000-00)
        REPORT_DATE DATETIME NOT NULL, # Data do relatório
        COMPANY_NAME TEXT NOT NULL, # Nome da empresa
        VERSION TEXT NOT NULL, # Versão
        ORDINARY_SHARES_ISSUED INTEGER NOT NULL, # Ações Ordinárias Emitidas
        ORDINARY_SHARES_TREASURY INTEGER NOT NULL, # Ações Ordinárias na Tesouraria
        PREFERRED_SHARES_ISSUED INTEGER NOT NULL, # Ações Preferenciais Emitidas
        PREFERRED_SHARES_TREASURY INTEGER NOT NULL, # Ações Preferenciais na Tesouraria
        TOTAL_SHARES_ISSUED INTEGER NOT NULL, # Total de Ações Emitidas
        TOTAL_SHARES_TREASURY INTEGER NOT NULL # Total de Ações na Tesouraria
    )

    Observações:
    - As informações estão disponibilizadas trimestralmente (Março, Junho, Setembro e Dezembro), conforme a data de início do período de análise.
    - Para o balanço anual, consultar análises de Dezembro.
    """
    return run_sql_query(inp, db_path=DB_PATH)
