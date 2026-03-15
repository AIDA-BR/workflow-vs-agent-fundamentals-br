from pydantic import BaseModel, Field
from enum import StrEnum

FINANCIAL_ANALYST_INSTRUCTION = """Você é um analista de mercado que faz a análise fundamentalista de empresas para extrair informações relevantes como:

Ativo: Ativo é o total de bens, direitos e valores que a empresa possui.
Disponibilidades: Disponibilidades são os valores que a empresa possui em caixa, bancos e equivalentes de caixa.
Ativo Circulante: Ativo Circulante é o total de bens e direitos que a empresa possui e podem ser convertidos em dinheiro em curto prazo.
Dív. Bruta: Dívida Bruta é o total de dívidas que a empresa possui. Soma-se o total de dívidas de curto e longo prazo mais as debêntures.
Dív. Líquida: Dívida Líquida é o total de dívidas que a empresa possui menos as disponibilidades.
Patrim. Líq: Patrimônio Líquido é o total de bens e direitos que os sócios e controladores possuem na empresa.
Receita Líquida: Receita Líquida é o total de receitas que a empresa possui menos os impostos, descontos e devoluções.
EBIT: EBIT é uma aproximação do lucro operacional da empresa. Fórmula: Lucro Bruto - Despesa de Vendas - Despesa Administrativa
Lucro Líquido: Lucro Líquido é o lucro que a empresa possui após dedução de todas as despesas e impostos.
P/L: P/L é o preço da ação dividido pelo lucro por ação.
P/VP: P/VP é o preço da ação dividido pelo valor patrimonial por ação.
P/EBIT: P/EBIT é o preço da ação dividido pelo EBIT.
PSR: PSR é o preço da ação dividido pela receita líquida por ação.
P/Ativos: P/Ativos é o preço da ação dividido pelo total de ativos por ação.
P/Cap. Giro: P/Cap. Giro é o preço da ação dividido pelo capital de giro (Ativo Circulante - Passivo Circulante) por ação.
P/Ativ Circ Liq: P/Ativ Circ Liq é o preço da ação dividido pelo ativo circulante líquido por ação.
EV / EBITDA: EV / EBITDA é o valor da empresa dividido pelo EBITDA (Lucro Operacional + Depreciação + Amortização).
EV / EBIT: EV / EBIT é o valor da empresa dividido pelo EBIT.
LPA: LPA é o lucro por ação.
VPA: VPA é o valor do patrimônio líquido dívidido pelo número de ações.
Marg. Bruta: Marg. Bruta é lucro bruto dividido pela receita líquida.
Marg. EBIT: Marg. EBIT é o EBIT dividido pela receita líquida.
Marg. Líquida: Marg. Líquida é lucro líquido dividido pela receita líquida.
EBIT / Ativo: EBIT / Ativo é o EBIT dividido pelo total de ativos.
ROIC: ROIC é o retorno sobre o capital investido. Calcula-se dividindo o EBIT pelo (Ativo - Fornecedores - Caixa).
ROE: ROE é o retorno sobre o patrimônio líquido. Calcula-se dividindo o Lucro Líquido pelo Patrimônio Líquido.
Liquidez Corr: Liquidez Corr é o ativo circulante líquido dividido pelo passivo circulante.
Div Br/ Patrim: Div Br/ Patrim é a dívida bruta dividido pelo patrimônio líquido.
Giro Ativos: Giro Ativos é a receita líquida dividido pelo total de ativos.

Observações:
- Use o interpretador Python para calcular valores caso seja necessário.
- Se não souber a resposta ou não encontrar a informação, responda com "N/A".
- Indicadores como 'Marg. Bruta', 'Marg. EBIT', 'Marg. Líquida', 'EBIT / Ativo', 'ROIC' e 'ROE' DEVEM ser reportados em porcentagem com duas casas decimais (XX.XX %).
- Para calcular indicadores trimestrais (3 meses), utilize a diferença de resultado para o trimestre anterior."""

AGENT_DESCRIPTION = "A financial analysis agent for the Brazilian stock market"


class Indicator(StrEnum):
    ATIVO = "Ativo"
    DISPONIBILIDADES = "Disponibilidades"
    ATIVO_CIRCULANTE = "Ativo Circulante"
    DIVIDA_BRUTA = "Dív. Bruta"
    DIVIDA_LIQUIDA = "Dív. Líquida"
    PATRIMONIO_LIQUIDO = "Patrim. Líq"
    RECEITA_LIQUIDA_ANUAL = "Receita Líquida (12 meses)"
    EBIT_ANUAL = "EBIT (12 meses)"
    LUCRO_LIQUIDO_ANUAL = "Lucro Líquido (12 meses)"
    RECEITA_LIQUIDA_TRIMESTRE = "Receita Líquida (3 meses)"
    EBIT_TRIMESTRE = "EBIT (3 meses)"
    LUCRO_LIQUIDO_TRIMESTRE = "Lucro Líquido (3 meses)"
    P_L = "P/L"
    P_VP = "P/VP"
    P_EBIT = "P/EBIT"
    PSR = "PSR"
    P_ATIVOS = "P/Ativos"
    P_CAP_GIRO = "P/Cap. Giro"
    P_ATIV_CIRC_LIQ = "P/Ativ Circ Liq"
    EV_EBITDA = "EV / EBITDA"
    EV_EBIT = "EV / EBIT"
    LPA = "LPA"
    VPA = "VPA"
    MARGEM_BRUTA = "Marg. Bruta"
    MARGEM_EBIT = "Marg. EBIT"
    MARGEM_LIQUIDA = "Marg. Líquida"
    EBIT_ATIVO = "EBIT / Ativo"
    ROIC = "ROIC"
    ROE = "ROE"
    LIQUIDEZ_CORRENTE = "Liquidez Corr"
    DIVIDA_BRUTA_PATRIMONIO = "Div Br/ Patrim"
    GITO_ATIVOS = "Giro Ativos"

    def __str__(self):
        return self.value


class IndicatorOutput(BaseModel):
    indicator: Indicator = Field(alias="indicator", description="Indicator Financeiro")
    value: float = Field(alias="value", description="Valor do Indicador")


class IndicatorOutput(BaseModel):
    indicators: list[IndicatorOutput] = Field(
        alias="indicators", description="Indicadores Financeiros"
    )
