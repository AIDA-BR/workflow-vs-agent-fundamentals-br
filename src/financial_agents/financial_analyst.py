from pydantic import BaseModel, Field
from enum import StrEnum

FINANCIAL_ANALYST_INSTRUCTION = """Você é um analista de mercado especializado em análise fundamentalista de ações brasileiras.

Todos os indicadores financeiros já foram obtidos diretamente do banco de dados contábil (CVM).
Não há campos a extrair do relatório nesta etapa."""

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
    """All base fields now come from the DB. No LLM extraction required."""

    def __str__(self):
        return self.value


# Keys used in db_fields dict passed to compute_indicators()
DB_ATIVO = "Ativo"
DB_DISPONIBILIDADES = "Disponibilidades"
DB_ATIVO_CIRCULANTE = "Ativo Circulante"
DB_PASSIVO_CIRCULANTE = "Passivo Circulante"
DB_DIVIDA_BRUTA = "Dív. Bruta"
DB_PATRIMONIO_LIQUIDO = "Patrim. Líq"
DB_FORNECEDORES = "Fornecedores"
DB_RECEITA_LIQUIDA_ANUAL = "Receita Líquida (12 meses)"
DB_LUCRO_BRUTO_ANUAL = "Lucro Bruto (12 meses)"
DB_EBIT_ANUAL = "EBIT (12 meses)"
DB_EBITDA_ANUAL = "EBITDA (12 meses)"
DB_LUCRO_LIQUIDO_ANUAL = "Lucro Líquido (12 meses)"
DB_RECEITA_LIQUIDA_TRIMESTRE = "Receita Líquida (3 meses)"
DB_EBIT_TRIMESTRE = "EBIT (3 meses)"
DB_LUCRO_LIQUIDO_TRIMESTRE = "Lucro Líquido (3 meses)"


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
    _raw: RawIndicatorOutput,
    db_fields: dict[str, float],
    price: float,
    total_shares: float,
) -> IndicatorOutput:
    """Computes all derived financial indicators entirely from DB-fetched base data.

    Args:
        raw: Unused — kept for API compatibility. All fields now come from db_fields.
        db_fields: The 15 base fields fetched directly from the CVM database. Use DB_* constants as keys.
        price: Stock price in BRL.
        total_shares: Number of outstanding shares.
    """
    # --- 15 fields from DB ---
    ativo = db_fields.get(DB_ATIVO, 0.0)
    disponibilidades = db_fields.get(DB_DISPONIBILIDADES, 0.0)
    ativo_circulante = db_fields.get(DB_ATIVO_CIRCULANTE, 0.0)
    passivo_circulante = db_fields.get(DB_PASSIVO_CIRCULANTE, 0.0)
    divida_bruta = db_fields.get(DB_DIVIDA_BRUTA, 0.0)
    patrimonio_liquido = db_fields.get(DB_PATRIMONIO_LIQUIDO, 0.0)
    fornecedores = db_fields.get(DB_FORNECEDORES, 0.0)
    receita_liquida_anual = db_fields.get(DB_RECEITA_LIQUIDA_ANUAL, 0.0)
    lucro_bruto_anual = db_fields.get(DB_LUCRO_BRUTO_ANUAL, 0.0)
    ebit_anual = db_fields.get(DB_EBIT_ANUAL, 0.0)
    ebitda_anual = db_fields.get(DB_EBITDA_ANUAL, 0.0)
    lucro_liquido_anual = db_fields.get(DB_LUCRO_LIQUIDO_ANUAL, 0.0)
    receita_liquida_trimestre = db_fields.get(DB_RECEITA_LIQUIDA_TRIMESTRE, 0.0)
    ebit_trimestre = db_fields.get(DB_EBIT_TRIMESTRE, 0.0)
    lucro_liquido_trimestre = db_fields.get(DB_LUCRO_LIQUIDO_TRIMESTRE, 0.0)

    # --- Derived intermediaries ---
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
