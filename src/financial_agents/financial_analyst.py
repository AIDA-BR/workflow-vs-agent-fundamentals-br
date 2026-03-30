from pydantic import BaseModel, Field
from enum import StrEnum

FINANCIAL_ANALYST_INSTRUCTION = """Você é um analista de mercado especializado em extrair dados financeiros brutos de relatórios DFP/ITR da CVM.

Sua tarefa é SOMENTE extrair os valores brutos dos seguintes indicadores diretamente do relatório fornecido:

Ativo: Total de bens, direitos e valores que a empresa possui (conta 1 do Balanço Patrimonial).
Disponibilidades: Valores em caixa, bancos e equivalentes de caixa.
Ativo Circulante: Total de bens e direitos de curto prazo (conta 1.01 do Balanço Patrimonial).
Passivo Circulante: Total de obrigações de curto prazo (conta 2.01 do Balanço Patrimonial).
Dív. Bruta: Total de dívidas — soma das dívidas de curto e longo prazo mais debêntures.
Patrim. Líq: Patrimônio Líquido — total de bens e direitos dos sócios (conta 2.03 do Balanço Patrimonial).
Receita Líquida (12 meses): Receita Líquida acumulada dos últimos 12 meses.
Lucro Bruto (12 meses): Lucro Bruto acumulado dos últimos 12 meses (Receita Líquida - Custo dos Produtos Vendidos).
EBIT (12 meses): Lucro antes de juros e impostos — Lucro Bruto menos Despesas de Vendas e Administrativas, acumulado dos últimos 12 meses.
EBITDA (12 meses): EBIT mais Depreciação e Amortização, acumulado dos últimos 12 meses.
Lucro Líquido (12 meses): Lucro Líquido acumulado dos últimos 12 meses.
Receita Líquida (3 meses): Receita Líquida do trimestre atual.
EBIT (3 meses): EBIT do trimestre atual.
Lucro Líquido (3 meses): Lucro Líquido do trimestre atual.
Fornecedores: Valor de contas a pagar a fornecedores (Passivo Circulante).

Observações:
- Extraia APENAS os valores diretamente do relatório. Não calcule nem derive indicadores compostos.
- Para indicadores trimestrais (3 meses), utilize a diferença entre o resultado do período atual e o trimestre anterior quando o relatório apresentar valores acumulados.
- Se não encontrar o valor no relatório, retorne 0.
- Todos os valores monetários devem ser reportados na mesma unidade do relatório (geralmente R$ mil)."""

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
    GIRO_ATIVOS = "Giro Ativos"

    def __str__(self):
        return self.value


class RawIndicator(StrEnum):
    ATIVO = "Ativo"
    DISPONIBILIDADES = "Disponibilidades"
    ATIVO_CIRCULANTE = "Ativo Circulante"
    PASSIVO_CIRCULANTE = "Passivo Circulante"
    DIVIDA_BRUTA = "Dív. Bruta"
    PATRIMONIO_LIQUIDO = "Patrim. Líq"
    RECEITA_LIQUIDA_ANUAL = "Receita Líquida (12 meses)"
    LUCRO_BRUTO_ANUAL = "Lucro Bruto (12 meses)"
    EBIT_ANUAL = "EBIT (12 meses)"
    EBITDA_ANUAL = "EBITDA (12 meses)"
    LUCRO_LIQUIDO_ANUAL = "Lucro Líquido (12 meses)"
    RECEITA_LIQUIDA_TRIMESTRE = "Receita Líquida (3 meses)"
    EBIT_TRIMESTRE = "EBIT (3 meses)"
    LUCRO_LIQUIDO_TRIMESTRE = "Lucro Líquido (3 meses)"
    FORNECEDORES = "Fornecedores"

    def __str__(self):
        return self.value


class IndicatorValue(BaseModel):
    indicator: Indicator = Field(alias="indicator", description="Indicador Financeiro")
    value: float = Field(alias="value", description="Valor do Indicador")


class IndicatorOutput(BaseModel):
    indicators: list[IndicatorValue] = Field(
        alias="indicators", description="Indicadores Financeiros"
    )


class RawIndicatorValue(BaseModel):
    indicator: RawIndicator = Field(alias="indicator", description="Indicador Financeiro Bruto")
    value: float = Field(alias="value", description="Valor do Indicador")


class RawIndicatorOutput(BaseModel):
    indicators: list[RawIndicatorValue] = Field(
        alias="indicators", description="Indicadores Financeiros Brutos"
    )


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0.0:
        return 0.0
    return numerator / denominator


def compute_indicators(
    raw: RawIndicatorOutput,
    price: float,
    total_shares: float,
) -> IndicatorOutput:
    """Computes all derived financial indicators from raw LLM-extracted base data."""
    raw_map = {str(i.indicator): i.value for i in raw.indicators}

    ativo = raw_map.get(str(RawIndicator.ATIVO), 0.0)
    disponibilidades = raw_map.get(str(RawIndicator.DISPONIBILIDADES), 0.0)
    ativo_circulante = raw_map.get(str(RawIndicator.ATIVO_CIRCULANTE), 0.0)
    passivo_circulante = raw_map.get(str(RawIndicator.PASSIVO_CIRCULANTE), 0.0)
    divida_bruta = raw_map.get(str(RawIndicator.DIVIDA_BRUTA), 0.0)
    patrimonio_liquido = raw_map.get(str(RawIndicator.PATRIMONIO_LIQUIDO), 0.0)
    receita_liquida_anual = raw_map.get(str(RawIndicator.RECEITA_LIQUIDA_ANUAL), 0.0)
    lucro_bruto_anual = raw_map.get(str(RawIndicator.LUCRO_BRUTO_ANUAL), 0.0)
    ebit_anual = raw_map.get(str(RawIndicator.EBIT_ANUAL), 0.0)
    ebitda_anual = raw_map.get(str(RawIndicator.EBITDA_ANUAL), 0.0)
    lucro_liquido_anual = raw_map.get(str(RawIndicator.LUCRO_LIQUIDO_ANUAL), 0.0)
    receita_liquida_trimestre = raw_map.get(str(RawIndicator.RECEITA_LIQUIDA_TRIMESTRE), 0.0)
    ebit_trimestre = raw_map.get(str(RawIndicator.EBIT_TRIMESTRE), 0.0)
    lucro_liquido_trimestre = raw_map.get(str(RawIndicator.LUCRO_LIQUIDO_TRIMESTRE), 0.0)
    fornecedores = raw_map.get(str(RawIndicator.FORNECEDORES), 0.0)

    divida_liquida = divida_bruta - disponibilidades
    market_cap = price * total_shares
    passivo_total = ativo - patrimonio_liquido
    ev = market_cap + divida_liquida
    lpa = _safe_div(lucro_liquido_anual, total_shares)
    vpa = _safe_div(patrimonio_liquido, total_shares)
    capital_giro = ativo_circulante - passivo_circulante
    ativ_circ_liq = ativo_circulante - passivo_total
    roic_base = ativo - fornecedores - disponibilidades

    indicators = [
        IndicatorValue(indicator=Indicator.ATIVO, value=ativo),
        IndicatorValue(indicator=Indicator.DISPONIBILIDADES, value=disponibilidades),
        IndicatorValue(indicator=Indicator.ATIVO_CIRCULANTE, value=ativo_circulante),
        IndicatorValue(indicator=Indicator.DIVIDA_BRUTA, value=divida_bruta),
        IndicatorValue(indicator=Indicator.DIVIDA_LIQUIDA, value=divida_liquida),
        IndicatorValue(indicator=Indicator.PATRIMONIO_LIQUIDO, value=patrimonio_liquido),
        IndicatorValue(indicator=Indicator.RECEITA_LIQUIDA_ANUAL, value=receita_liquida_anual),
        IndicatorValue(indicator=Indicator.EBIT_ANUAL, value=ebit_anual),
        IndicatorValue(indicator=Indicator.LUCRO_LIQUIDO_ANUAL, value=lucro_liquido_anual),
        IndicatorValue(
            indicator=Indicator.RECEITA_LIQUIDA_TRIMESTRE, value=receita_liquida_trimestre
        ),
        IndicatorValue(indicator=Indicator.EBIT_TRIMESTRE, value=ebit_trimestre),
        IndicatorValue(indicator=Indicator.LUCRO_LIQUIDO_TRIMESTRE, value=lucro_liquido_trimestre),
        IndicatorValue(indicator=Indicator.LPA, value=lpa),
        IndicatorValue(indicator=Indicator.VPA, value=vpa),
        IndicatorValue(indicator=Indicator.P_L, value=_safe_div(price, lpa)),
        IndicatorValue(indicator=Indicator.P_VP, value=_safe_div(price, vpa)),
        IndicatorValue(indicator=Indicator.P_EBIT, value=_safe_div(market_cap, ebit_anual)),
        IndicatorValue(indicator=Indicator.PSR, value=_safe_div(market_cap, receita_liquida_anual)),
        IndicatorValue(indicator=Indicator.P_ATIVOS, value=_safe_div(market_cap, ativo)),
        IndicatorValue(indicator=Indicator.P_CAP_GIRO, value=_safe_div(market_cap, capital_giro)),
        IndicatorValue(
            indicator=Indicator.P_ATIV_CIRC_LIQ, value=_safe_div(market_cap, ativ_circ_liq)
        ),
        IndicatorValue(indicator=Indicator.EV_EBITDA, value=_safe_div(ev, ebitda_anual)),
        IndicatorValue(indicator=Indicator.EV_EBIT, value=_safe_div(ev, ebit_anual)),
        IndicatorValue(
            indicator=Indicator.MARGEM_BRUTA,
            value=_safe_div(lucro_bruto_anual, receita_liquida_anual) * 100,
        ),
        IndicatorValue(
            indicator=Indicator.MARGEM_EBIT,
            value=_safe_div(ebit_anual, receita_liquida_anual) * 100,
        ),
        IndicatorValue(
            indicator=Indicator.MARGEM_LIQUIDA,
            value=_safe_div(lucro_liquido_anual, receita_liquida_anual) * 100,
        ),
        IndicatorValue(
            indicator=Indicator.EBIT_ATIVO,
            value=_safe_div(ebit_anual, ativo) * 100,
        ),
        IndicatorValue(
            indicator=Indicator.ROIC,
            value=_safe_div(ebit_anual, roic_base) * 100,
        ),
        IndicatorValue(
            indicator=Indicator.ROE,
            value=_safe_div(lucro_liquido_anual, patrimonio_liquido) * 100,
        ),
        IndicatorValue(
            indicator=Indicator.LIQUIDEZ_CORRENTE,
            value=_safe_div(ativo_circulante, passivo_circulante),
        ),
        IndicatorValue(
            indicator=Indicator.DIVIDA_BRUTA_PATRIMONIO,
            value=_safe_div(divida_bruta, patrimonio_liquido),
        ),
        IndicatorValue(
            indicator=Indicator.GIRO_ATIVOS,
            value=_safe_div(receita_liquida_anual, ativo),
        ),
    ]
    return IndicatorOutput(indicators=indicators)
