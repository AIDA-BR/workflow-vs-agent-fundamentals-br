"""Monta a amostra de 200 notícias da busca ambiental para a anotação manual.

Três estratos, todos entre notícias que citam a empresa:

* ``titulo``: termo ambiental no título (80);
* ``so_texto``: termo só no texto (80);
* ``sem_termo``: nenhum termo da lista (40), para medir o que a lista deixa passar.

Dentro de cada estrato a cota por empresa é proporcional à raiz do volume (como no piloto), para
as empresas pequenas aparecerem. A ordem final é embaralhada e o estrato não vai para a página, para
não influenciar a resposta.

Saídas:
* ``<out>/items.json``: o que a página mostra (id, empresa, data, fonte, título, link, texto);
* ``data/news/annotation_key.csv``: a chave local (id → notícia, estrato, grupos da lista).

    cd news_signal && uv run annotation_sample.py --out <pasta da página>
"""

import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

import lexicon
from clean_texts import CLEAN_DB
from fetch_bodies import NEWS_DIR, pilot_sample

STRATA = {"titulo": 80, "so_texto": 80, "sem_termo": 40}
MAX_CHARS = 5000
KEY_PATH = NEWS_DIR / "annotation_key.csv"


def load(path: Path = CLEAN_DB) -> pd.DataFrame:
    query = "SELECT * FROM articles WHERE kind = 'env' AND dup_of IS NULL"
    df = pd.read_sql(query, sqlite3.connect(path))
    for col in ("mentions_company", "env_title", "env_text", "has_text"):
        df[col] = df[col].astype(bool)
    df = df[df.mentions_company].copy()
    df["stratum"] = np.select([df.env_title, df.env_text], ["titulo", "so_texto"], "sem_termo")
    return df


def sample(df: pd.DataFrame, sizes: dict[str, int] = STRATA, seed: int = 7) -> pd.DataFrame:
    picked = []
    for stratum, n in sizes.items():
        pool = df[(df.stratum == stratum) & df.has_text]
        by_company = pool.rename(columns={"source": "_source", "ticker": "source"})
        picked.extend(pilot_sample(by_company, min(n, len(pool)), seed))
    out = df[df.gnews_url.isin(picked)].sample(frac=1, random_state=seed).reset_index(drop=True)
    out["item_id"] = [f"n{i + 1:03d}" for i in range(len(out))]
    return out


def to_items(df: pd.DataFrame, max_chars: int = MAX_CHARS) -> list[dict]:
    items = []
    for r in df.itertuples():
        text = r.text_clean or ""
        items.append(
            {
                "id": r.item_id,
                "ticker": r.ticker,
                "date": r.published_at[:10],
                "source": r.source,
                "title": r.title_clean,
                "url": r.decoded_url,
                "text": text[:max_chars],
                "truncated": len(text) > max_chars,
            }
        )
    return items


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, required=True, help="pasta onde gravar items.json")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    chosen = sample(load(), seed=args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / "items.json", "w", encoding="utf-8") as f:
        json.dump(to_items(chosen), f, ensure_ascii=False)

    cats = [f"env_{w}_{c}" for w in ("title", "text") for c in lexicon.CATEGORIES]
    key = chosen[["item_id", "gnews_url", "ticker", "published_at", "stratum", *cats]]
    key.to_csv(KEY_PATH, index=False)
    print(f"{len(chosen)} notícias: {chosen.stratum.value_counts().to_dict()}")
    print("por empresa:", chosen.ticker.value_counts().to_dict())
    print(
        f"items.json: {(args.out / 'items.json').stat().st_size / 1024:.0f} KB | chave: {KEY_PATH}"
    )


if __name__ == "__main__":
    main()
