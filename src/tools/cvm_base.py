from agents import function_tool

from src.db.base_query import QueryInput, run_sql_query
from src.settings import DB_PATH


@function_tool
def cvm_base_query_tool(inp: QueryInput) -> dict:
    """Consultar um Banco de Dados SQL de Formulários de Demonstrações Financeiras Padronizadas (DFP) e Formulário de Informações Trimestrais (ITR) do Mercado de Ações Brasileiro com o seguinte esquema:

    CREATE TABLE IF NOT EXISTS DFP_ITR_CVM (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        CNPJ TEXT NOT NULL, # CNPJ da empresa (Formato 00.000.000/0000-00)
        REPORT_DATE DATETIME NOT NULL, # Data do relatório
        COMPANY_NAME TEXT NOT NULL, # Nome da empresa
        CVM_CODE TEXT NOT NULL, # CVM Code
        DFP_GROUP TEXT NOT NULL, # Grupo DFP
        VERSION TEXT NOT NULL, # Versão
        CURRENCY TEXT NOT NULL, # Moeda
        EXERC_ORDER TEXT NOT NULL, # Ordem de Exercício (Penúltimo ou Último)
        ANALYSIS_START_PERIOD_DATE DATETIME, # Data de Início do Período de Análise
        ANALYSIS_END_PERIOD_DATE DATETIME NOT NULL, # Data de Fim do Período de Análise
        ACCOUNT_NUMBER TEXT NOT NULL, # Número da Conta
        ACCOUNT_NAME TEXT NOT NULL, # Nome da Conta
        ACCOUNT_VALUE FLOAT NOT NULL, # Valor da Conta
        IS_FIXED_ACCOUNT TEXT # Conta Fixa?
    )

    Observações:
    - O número da conta (ACCOUNT_NUMBER) contém a informação de ordem e hierarquia dos números do balanço. Além das datas, considere esta informação para ordernar os relatórios.
    - As informações estão disponibilizadas trimestralmente (Março, Junho, Setembro e Dezembro), conforme a data de início do período de análise.
    - Para o balanço anual, consultar análises de Dezembro.
    """
    return run_sql_query(inp, db_path=DB_PATH)
