"""Lista de termos ambientais (versão 0), em grupos que podem mover o preço em direções diferentes.

É um ponto de partida para a anotação manual: a anotação mede onde a lista erra, e os erros viram
termos mais precisos ou exclusões. Termos genéricos do negócio (por exemplo "energia renovável" numa
geradora) ficam de fora de propósito, porque aparecem em quase toda notícia da empresa.
"""

import re
import unicodedata

#: grupo → expressões regulares (aplicadas a texto sem acento e em minúsculas).
CATEGORIES: dict[str, tuple[str, ...]] = {
    "incidente_sancao": (
        r"multa\w* (ambienta|do ibama|pelo ibama)",
        r"ibama .{0,60}multa|multa\w* .{0,60}ibama",
        r"auto de infracao|infracao ambienta",
        r"crime ambienta|dano\w* ambienta|desastre ambienta|tragedia ambienta",
        r"vazamento de (oleo|petroleo|fluido|rejeito|gas|combustivel|diesel)",
        r"derramamento",
        r"rompimento d[ae] barragem|barragem .{0,40}(rompimento|risco|emergencia|interdi)",
        r"contamina\w*",
        r"polui\w*",
        r"desmatamento|queimada",
        r"acao civil publica",
        r"embargo ambienta|interdi\w* .{0,40}ambienta",
    ),
    "licenciamento": (
        r"licenca (ambienta|de operacao|de instalacao|previa|de perfuracao|para perfurar)",
        r"licenciamento",
        r"(autoriza\w*|aval|aprova\w*) d[oa] ibama|ibama (autoriza|aprova|libera|nega|rejeita)",
        r"\beia\b|\brima\b|estudo de impacto ambienta",
    ),
    "transicao": (
        r"descarboniza\w*",
        r"emissoes (de carbono|de co2|de gases|de gee|de efeito estufa)|gases de efeito estufa",
        r"credito\w* de carbono|captura de carbono|\bccus\b|baixo carbono|carbono neutro|net zero",
        r"transicao energetica",
        r"hidrogenio verde|combustive\w* sustentave\w*|\bsaf\b",
    ),
    "esg": (
        r"\besg\b",
        r"relatorio de sustentabilidade|indice de sustentabilidade|\bise b3\b|\bcdp\b",
        r"sustentabilidade",
    ),
    "clima_hidrico": (
        r"\bseca\b|estiagem|crise hidrica|risco hidrologico|\bgsf\b",
        r"enchente|inundac\w*|chuvas? (intensas?|extremas?)",
        r"reservatorios?",
        r"mudancas? climatica|evento\w* climatico\w* extremo|el nino|la nina",
    ),
}

_COMPILED = {cat: [re.compile(p) for p in pats] for cat, pats in CATEGORIES.items()}


def fold(text: str) -> str:
    """Minúsculas e sem acento, para os termos casarem com e sem acentuação."""
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def match(text: str) -> dict[str, int]:
    """Número de ocorrências por grupo (só grupos com ao menos uma)."""
    folded = fold(text)
    hits = {}
    for cat, patterns in _COMPILED.items():
        n = sum(len(p.findall(folded)) for p in patterns)
        if n:
            hits[cat] = n
    return hits
