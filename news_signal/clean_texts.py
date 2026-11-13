"""Limpa os textos baixados, verifica se a empresa é citada e marca os termos ambientais.

Lê ``data/news/bodies.sqlite`` e grava ``data/news/clean.sqlite`` (tabela ``articles``), uma linha
por notícia, inclusive as duplicatas, que herdam o texto da notícia canônica.

Limpeza do texto:

* linhas de "leia também", "veja também", publicidade e afins são removidas, junto com a lista de
  manchetes que costuma vir logo depois. Isso importa porque a página foi baixada meses depois e
  essas listas podem citar notícias posteriores (vazamento de informação do futuro);
* o texto é cortado no primeiro marcador de rodapé ("mais lidas", "notícias relacionadas", ...);
* texto que fica curto demais depois da limpeza é tratado como sem texto.

Citação da empresa: o título ou o texto precisa citar o ticker (qualquer classe, PETR3 ou PETR4) ou
o nome da empresa, com exclusões de homônimos (Vale do Jequitinhonha, Margem Equatorial, ...).
Por enquanto os nomes só existem para as 9 ações do paper; as demais checam só o ticker.

    cd news_signal && uv run clean_texts.py
"""

import argparse
import re
import sqlite3
from pathlib import Path

import pandas as pd

import lexicon
from fetch_bodies import DEFAULT_DB, NEWS_DIR, strip_source

CLEAN_DB = NEWS_DIR / "clean.sqlite"
MIN_CLEAN_CHARS = 400

#: Linha que é chamada para outra notícia ou peça de navegação: sai, e a lista que vem depois também.
_LINK_LINE = re.compile(
    r"^\W*(leia (tamb[eé]m|mais|ainda)|veja (tamb[eé]m|mais)|saiba mais|confira (tamb[eé]m|mais)|"
    r"relacionad[ao]s?|recomendad[ao]s?|assista|ou[cç]a|leia o pr[oó]ximo)\b",
    re.I,
)
#: Linha de publicidade ou chamada de inscrição: sai sozinha.
_NOISE_LINE = re.compile(
    r"^\W*(continua depois da publicidade|publicidade|an[uú]ncio|siga[- ]nos|siga o|"
    r"inscreva-se|receba (as )?not[ií]cias|clique aqui|compartilh|quer receber)",
    re.I,
)
#: Marcador de rodapé: o texto termina aqui.
_END_LINE = re.compile(
    r"^\W*(mais lidas|not[ií]cias relacionadas|[uú]ltimas not[ií]cias|voc[eê] (tamb[eé]m )?pode gostar|"
    r"tags?:|sobre o autor|mat[eé]rias relacionadas|leia o pr[oó]ximo artigo|newsletter)",
    re.I,
)


def _looks_like_headline(line: str) -> bool:
    """Item de lista de manchetes: curto, sem ponto final, às vezes com marcador."""
    text = line.strip().lstrip("-•*– ").strip()
    return 0 < len(text) <= 160 and not text.endswith((".", ":", ";", "?", "!", '"', "”"))


def clean_text(text: str | None) -> str | None:
    if not isinstance(text, str) or not text:
        return None
    kept: list[str] = []
    skipping_list = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            skipping_list = False
            continue
        if _END_LINE.match(line):
            break
        if _LINK_LINE.match(line):
            skipping_list = True
            continue
        if skipping_list and _looks_like_headline(line):
            continue
        skipping_list = False
        if _NOISE_LINE.match(line):
            continue
        if line.startswith(("- -", "• •")):
            continue
        kept.append(line)
    cleaned = "\n".join(kept).strip()
    return cleaned if len(cleaned) >= MIN_CLEAN_CHARS else None


#: Nomes das 9 ações do paper: (padrão do nome, padrões de homônimos que não contam).
COMPANY_NAMES: dict[str, tuple[str, tuple[str, ...]]] = {
    "ALUP11": (r"\balupar\b", ()),
    "AURE3": (r"\bauren\b", (r"\bauren hoffman",)),
    "CPLE3": (r"\bcopel\b", (r"bosque da copel",)),
    "EALT4": (r"\b(electro )?a[cç]o altona\b|\baltona\b", ()),
    "ENEV3": (r"\beneva\b", ()),
    "EQTL3": (
        r"\bequatorial\b",
        (r"margem equatorial", r"guin[eé] equatorial", r"faixa equatorial"),
    ),
    "PETR4": (r"\bpetrobr[aá]s\b|petr[oó]leo brasileiro", ()),
    "RECV3": (r"\bpetro ?rec[oô]ncavo\b", ()),
    "VALE3": (
        r"\bVale\b",
        (
            r"\bVale d[oaei]s?\b",
            r"\b(Alto|M[eé]dio|Baixo) Vale\b",
            r"\bVale (a pena|lembrar|ressaltar|destacar|dizer|notar|mencionar|salientar|observar|registrar)",
        ),
    ),
}
#: Nomes de pessoa ou lugar são sensíveis a maiúsculas ("vale a pena" ≠ "Vale").
_CASE_SENSITIVE = {"VALE3"}


def ticker_pattern(ticker: str) -> re.Pattern:
    """Qualquer classe da mesma empresa: PETR3, PETR4, ALUP11, ..."""
    return re.compile(rf"\b{re.escape(ticker[:4])}\d{{1,2}}\b", re.I)


def count_mentions(text: str | None, ticker: str) -> int:
    if not isinstance(text, str) or not text:
        return 0
    n = len(ticker_pattern(ticker).findall(text))
    if ticker in COMPANY_NAMES:
        name, exclusions = COMPANY_NAMES[ticker]
        flags = 0 if ticker in _CASE_SENSITIVE else re.I
        masked = text
        for pattern in exclusions:
            masked = re.sub(pattern, " ", masked, flags=flags)
        n += len(re.findall(name, masked, flags=flags))
    return n


def build(bodies_db: Path = DEFAULT_DB) -> pd.DataFrame:
    src = sqlite3.connect(bodies_db)
    df = pd.read_sql(
        "SELECT gnews_url, ticker, title, source, published_at, origem, kind, priority, dup_of,"
        " decode_status, fetch_status, decoded_url, domain, text, meta_date FROM bodies",
        src,
    )
    # Duplicatas herdam o resultado do download da notícia canônica.
    canonical = df.set_index("gnews_url")[
        ["fetch_status", "decoded_url", "domain", "text", "meta_date"]
    ]
    dups = df.dup_of.notna()
    for col in canonical.columns:
        df.loc[dups, col] = df.loc[dups, "dup_of"].map(canonical[col]).to_numpy()

    df["title_clean"] = df.title.map(strip_source)
    df["text_clean"] = [
        clean_text(t) if s == "ok" else None for t, s in zip(df.text, df.fetch_status)
    ]
    df["has_text"] = df.text_clean.notna()
    df["mentions_title"] = [count_mentions(t, k) for t, k in zip(df.title_clean, df.ticker)]
    df["mentions_text"] = [count_mentions(t, k) for t, k in zip(df.text_clean, df.ticker)]
    df["mentions_company"] = (df.mentions_title + df.mentions_text) > 0

    for where, col in (("title", "title_clean"), ("text", "text_clean")):
        hits = [lexicon.match(t) if isinstance(t, str) else {} for t in df[col]]
        for cat in lexicon.CATEGORIES:
            df[f"env_{where}_{cat}"] = [h.get(cat, 0) for h in hits]
    title_cols = [f"env_title_{c}" for c in lexicon.CATEGORIES]
    text_cols = [f"env_text_{c}" for c in lexicon.CATEGORIES]
    df["env_title"] = df[title_cols].sum(axis=1) > 0
    df["env_text"] = df[text_cols].sum(axis=1) > 0
    return df.drop(columns=["text"])


def summary(df: pd.DataFrame) -> str:
    env = df[(df.kind == "env") & df.dup_of.isna()]
    lines = [
        f"notícias: {len(df)} ({df.dup_of.isna().sum()} canônicas)",
        f"busca ambiental (canônicas): {len(env)}; com texto limpo: {env.has_text.sum()}; "
        f"citam a empresa: {env.mentions_company.sum()}",
        f"  termo ambiental no título: {env.env_title.sum()}; só no texto: {(env.env_text & ~env.env_title).sum()}; "
        f"nenhum: {(~env.env_title & ~env.env_text).sum()}",
    ]
    relevant = env[env.mentions_company & (env.env_title | env.env_text)]
    lines.append(f"  citam a empresa e têm termo ambiental: {len(relevant)}")
    for cat in lexicon.CATEGORIES:
        n = ((relevant[f"env_title_{cat}"] + relevant[f"env_text_{cat}"]) > 0).sum()
        lines.append(f"    {cat}: {n}")
    lines.append("  por empresa: " + relevant.ticker.value_counts().to_dict().__repr__())
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--bodies", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=CLEAN_DB)
    args = parser.parse_args()
    df = build(args.bodies)
    with sqlite3.connect(args.out) as out:
        df.to_sql("articles", out, if_exists="replace", index=False)
    print(summary(df))
    print(f"gravado: {args.out}")


if __name__ == "__main__":
    main()
