"""Fase 1: baixa o texto completo das notícias, localmente e sem passar pela produção.

Etapas, todas retomáveis (o estado fica em ``data/news/bodies.sqlite``):

1. ``init``: monta a lista de notícias candidatas e marca duplicatas (mesmo título + fonte);
   * coleta ao vivo exportada da produção, de 09/05/2026 até o fim do calendário de preços;
   * busca ambiental do backfill (nov/2025–out/2026), para o objetivo 2.
2. ``decode``: troca o link ``news.google.com`` pelo link da editora (googlenewsdecoder);
3. ``fetch``: baixa a página da editora respeitando ``robots.txt``, com um pedido por vez por site
   e intervalo mínimo entre pedidos, sem contornar paywall, e extrai o texto com trafilatura;
4. ``report``: taxas de sucesso por etapa e por site, e uma amostra para revisão manual.

Os textos ficam fora do git: o paper publica só features e URLs.

    cd news_signal
    uv run fetch_bodies.py init
    uv run fetch_bodies.py decode --pilot 500
    uv run fetch_bodies.py fetch
    uv run fetch_bodies.py report
"""

import argparse
import asyncio
import json
import logging
import math
import re
import sqlite3
import time
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence
from urllib.parse import urlsplit

import pandas as pd

logger = logging.getLogger("fetch_bodies")

REPO_ROOT = Path(__file__).resolve().parents[1]
NEWS_DIR = REPO_ROOT / "data" / "news"
DEFAULT_DB = NEWS_DIR / "bodies.sqlite"
LIVE_EXPORT = NEWS_DIR / "stock_news_live.csv.gz"
BACKFILL_DBS = (NEWS_DIR / "backfill.sqlite", NEWS_DIR / "backfill_recall.sqlite")
#: Último pregão do bundle de preços (b3_latest.tar.gz): notícias depois disso não têm rótulo.
WINDOW_END = "2026-10-31"
PAPER9 = ("ALUP11", "AURE3", "CPLE3", "EALT4", "ENEV3", "EQTL3", "PETR4", "RECV3", "VALE3")

USER_AGENT = "Mozilla/5.0 (compatible; news-signal-research/0.1)"
ROBOTS_AGENT = "news-signal-research"
MAX_BYTES = 5_000_000
#: Abaixo disso o texto extraído é tratado como curto demais (paywall, página de erro, só lide).
MIN_CHARS = 500

SCHEMA = """
CREATE TABLE IF NOT EXISTS bodies (
    gnews_url TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    published_at TEXT NOT NULL,
    origem TEXT NOT NULL,
    kind TEXT NOT NULL,
    priority INTEGER NOT NULL,
    dup_of TEXT,
    pilot INTEGER NOT NULL DEFAULT 0,
    decode_status TEXT,
    decoded_url TEXT,
    domain TEXT,
    fetch_status TEXT,
    http_status INTEGER,
    text TEXT,
    n_chars INTEGER,
    meta_date TEXT,
    error TEXT,
    decoded_at TEXT,
    fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS bodies_todo ON bodies (dup_of, decode_status, fetch_status, priority);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path: Path | str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db


# ---------------------------------------------------------------------------
# init: candidatas e duplicatas
# ---------------------------------------------------------------------------


def strip_source(title: str) -> str:
    """Remove o sufixo " - Fonte" que o Google News acrescenta a todo título."""
    return re.sub(r"\s+-\s+[^-]+$", "", title).strip()


def dedup_key(title: str, source: str) -> str:
    text = re.sub(r"\W+", " ", strip_source(title).lower()).strip()
    return f"{source.strip().lower()}|{text}"


def load_live(path: Path = LIVE_EXPORT, end: str = WINDOW_END) -> pd.DataFrame:
    live = pd.read_csv(path, parse_dates=["published_at", "created_at"])
    start = live.created_at.min()
    live = live[(live.published_at >= start) & (live.published_at < end)]
    return pd.DataFrame(
        {
            "gnews_url": live.url,
            "ticker": live.ticker,
            "title": live.title,
            "source": live.source.fillna("Google News"),
            "published_at": live.published_at.map(lambda t: t.isoformat()),
            "origem": "live",
            "kind": "ticker",
        }
    )


def load_backfill_env(paths: Iterable[Path] = BACKFILL_DBS, end: str = WINDOW_END) -> pd.DataFrame:
    frames = []
    for path in paths:
        if Path(path).exists():
            query = (
                "SELECT url AS gnews_url, ticker, title, source, published_at FROM articles"
                " WHERE kind = 'env' AND published_at < ?"
            )
            frames.append(pd.read_sql(query, sqlite3.connect(path), params=(end,)))
    if not frames:
        return pd.DataFrame(columns=["gnews_url", "ticker", "title", "source", "published_at"])
    env = pd.concat(frames, ignore_index=True)
    return env.assign(origem="backfill", kind="env")


def priority_of(row) -> int:
    """0 = busca ambiental (objetivo 2); 1 = 9 ações do paper; 2 = demais."""
    if row.kind == "env":
        return 0
    return 1 if row.ticker in PAPER9 else 2


def build_candidates(frames: Sequence[pd.DataFrame]) -> pd.DataFrame:
    """Uma linha por link; o primeiro link de cada (título, fonte) é o canônico, os outros apontam
    para ele em ``dup_of`` e não são baixados.

    Um mesmo link pode vir da coleta ao vivo e da busca ambiental: fica a linha de maior prioridade
    (a ambiental), para o objetivo 2 saber que a notícia veio daquela busca.
    """
    df = pd.concat(frames, ignore_index=True)
    df["priority"] = df.apply(priority_of, axis=1)
    df = df.sort_values(["priority", "published_at"]).drop_duplicates("gnews_url", keep="first")
    key = [dedup_key(t, s) for t, s in zip(df.title, df.source)]
    canonical = pd.Series(df.gnews_url.to_numpy(), index=key).groupby(level=0).first()
    df["dup_of"] = [canonical[k] if canonical[k] != u else None for k, u in zip(key, df.gnews_url)]
    return df.reset_index(drop=True)


def init(db: sqlite3.Connection, frames: Sequence[pd.DataFrame]) -> int:
    df = build_candidates(frames)
    cols = ["gnews_url", "ticker", "title", "source", "published_at", "origem", "kind"]
    rows = df[cols + ["priority", "dup_of"]].itertuples(index=False, name=None)
    with db:
        before = db.total_changes
        db.executemany(
            f"INSERT OR IGNORE INTO bodies ({', '.join(cols)}, priority, dup_of)"
            f" VALUES ({', '.join('?' * (len(cols) + 2))})",
            rows,
        )
        return db.total_changes - before


def pilot_sample(df: pd.DataFrame, n: int, seed: int = 0) -> list[str]:
    """Amostra estratificada por fonte, com cota proporcional à raiz do volume de cada fonte.

    A raiz equilibra os dois objetivos do piloto: refletir as fontes que mais pesam e ainda assim
    ver sites diferentes o bastante para estimar a extração de cada um.
    """
    counts = df.source.value_counts()
    weights = counts.map(math.sqrt)
    quota = (weights / weights.sum() * n).map(math.ceil).clip(upper=counts)
    picked = []
    for source, k in quota.items():
        group = df[df.source == source]
        picked.extend(group.sample(int(k), random_state=seed).gnews_url)
    return picked[:n] if len(picked) <= n else list(pd.Series(picked).sample(n, random_state=seed))


def mark_pilot(db: sqlite3.Connection, n: int, seed: int = 0) -> int:
    if db.execute("SELECT count(*) FROM bodies WHERE pilot = 1").fetchone()[0]:
        return 0
    todo = pd.read_sql("SELECT gnews_url, source FROM bodies WHERE dup_of IS NULL", db)
    urls = pilot_sample(todo, n, seed)
    with db:
        db.executemany("UPDATE bodies SET pilot = 1 WHERE gnews_url = ?", [(u,) for u in urls])
    return len(urls)


# ---------------------------------------------------------------------------
# decode: link do Google → link da editora
# ---------------------------------------------------------------------------


def pending_decode(db: sqlite3.Connection, pilot_only: bool, limit: int | None) -> list[str]:
    query = "SELECT gnews_url FROM bodies WHERE dup_of IS NULL AND decode_status IS NULL"
    if pilot_only:
        query += " AND pilot = 1"
    query += " ORDER BY priority, published_at DESC"
    if limit:
        query += f" LIMIT {int(limit)}"
    return [r[0] for r in db.execute(query)]


def save_decoded(db: sqlite3.Connection, urls: Sequence[str], results: Sequence[dict]) -> int:
    ok = 0
    stamp = now()
    with db:
        for url, result in zip(urls, results):
            if result.get("success") and result.get("decoded_url"):
                decoded = result["decoded_url"]
                db.execute(
                    "UPDATE bodies SET decode_status='ok', decoded_url=?, domain=?, decoded_at=?"
                    " WHERE gnews_url=?",
                    (decoded, urlsplit(decoded).netloc.lower(), stamp, url),
                )
                ok += 1
            else:
                db.execute(
                    "UPDATE bodies SET decode_status='failed', error=?, decoded_at=? WHERE gnews_url=?",
                    (str(result.get("message", "sem mensagem"))[:500], stamp, url),
                )
    return ok


def decode(
    db: sqlite3.Connection,
    decode_batch: Callable[[list[str]], list[dict]],
    pilot_only: bool = False,
    limit: int | None = None,
    batch_size: int = 10,
    sleep: Callable[[float], None] = time.sleep,
    max_failed_batches: int = 4,
) -> tuple[int, int]:
    """Decodifica em lotes; um lote inteiro falhando é tratado como bloqueio e espera cada vez mais.

    Um lote que falha inteiro não é gravado, para ser tentado de novo depois.
    """
    urls = pending_decode(db, pilot_only, limit)
    done = failed_batches = 0
    for i in range(0, len(urls), batch_size):
        batch = urls[i : i + batch_size]
        results = decode_batch(batch)
        if not any(r.get("success") for r in results):
            failed_batches += 1
            if failed_batches > max_failed_batches:
                message = results[0].get("message") if results else ""
                logger.warning(
                    "Google recusou %d lotes seguidos (%s); parando.", failed_batches, message
                )
                break
            wait = 60 * 2 ** (failed_batches - 1)
            logger.warning("Lote inteiro falhou; esperando %ds", wait)
            sleep(wait)
            continue
        failed_batches = 0
        done += save_decoded(db, batch, results)
        if (i // batch_size) % 10 == 0:
            logger.warning("decodificados %d de %d", done, len(urls))
    return done, len(urls)


def google_decoder(interval: float):
    from googlenewsdecoder import GoogleDecoder

    client = GoogleDecoder(timeout=20.0)
    return client, lambda batch: client.decode_google_news_urls(batch, interval=interval)


# ---------------------------------------------------------------------------
# fetch: página da editora → texto
# ---------------------------------------------------------------------------


def classify(
    extracted: str | None, min_chars: int = MIN_CHARS
) -> tuple[str, str | None, int, str | None]:
    """(status, texto, n_chars, data do metadado) a partir do JSON do trafilatura."""
    if not extracted:
        return "empty", None, 0, None
    data = json.loads(extracted)
    text = (data.get("text") or "").strip()
    status = "ok" if len(text) >= min_chars else "short"
    return status, text or None, len(text), data.get("date")


def extract(html: str, url: str) -> str | None:
    import trafilatura

    return trafilatura.extract(
        html,
        url=url,
        output_format="json",
        with_metadata=True,
        favor_precision=True,
        include_comments=False,
        include_tables=False,
    )


class Robots:
    """robots.txt por site, com cache. 4xx = tudo liberado; erro de rede ou 5xx = nada liberado."""

    def __init__(self, client):
        self.client = client
        self.cache: dict[str, urllib.robotparser.RobotFileParser | bool] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    async def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        lock = self.locks.setdefault(base, asyncio.Lock())
        async with lock:
            if base not in self.cache:
                self.cache[base] = await self._load(base)
        rules = self.cache[base]
        if isinstance(rules, bool):
            return rules
        return rules.can_fetch(ROBOTS_AGENT, url)

    async def _load(self, base: str):
        try:
            response = await self.client.get(f"{base}/robots.txt", follow_redirects=True)
        except Exception:  # noqa: BLE001 — qualquer falha de rede bloqueia o site, por cautela
            return False
        if 400 <= response.status_code < 500:
            return True
        if response.status_code >= 500:
            return False
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser


class DomainPacer:
    """Um pedido por vez por site, com intervalo mínimo entre pedidos ao mesmo site."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self.locks: dict[str, asyncio.Lock] = {}
        self.last: dict[str, float] = {}

    async def __call__(self, domain: str):
        lock = self.locks.setdefault(domain, asyncio.Lock())
        await lock.acquire()
        wait = self.last.get(domain, 0) + self.min_interval - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        return lock

    def release(self, domain: str, lock: asyncio.Lock) -> None:
        self.last[domain] = time.monotonic()
        lock.release()


async def fetch_one(client, robots: Robots, pacer: DomainPacer, url: str, domain: str) -> dict:
    if not await robots.allowed(url):
        return {"fetch_status": "robots"}
    lock = await pacer(domain)
    try:
        response = await client.get(url, follow_redirects=True)
    except Exception as exc:  # noqa: BLE001 — erro de rede vira status, não derruba o lote
        return {"fetch_status": "error", "error": f"{type(exc).__name__}: {exc}"[:500]}
    finally:
        pacer.release(domain, lock)
    result = {"http_status": response.status_code}
    if response.status_code != 200:
        return {**result, "fetch_status": "http"}
    if "html" not in response.headers.get("content-type", "html"):
        return {**result, "fetch_status": "not_html"}
    if len(response.content) > MAX_BYTES:
        return {**result, "fetch_status": "too_big"}
    try:
        extracted = await asyncio.to_thread(extract, response.text, str(response.url))
        status, text, n_chars, meta_date = classify(extracted)
    except Exception as exc:  # noqa: BLE001 — HTML quebrado não derruba o lote
        return {**result, "fetch_status": "extract_error", "error": str(exc)[:500]}
    return {
        **result,
        "fetch_status": status,
        "text": text,
        "n_chars": n_chars,
        "meta_date": meta_date,
    }


def save_fetched(db: sqlite3.Connection, url: str, result: dict) -> None:
    fields = ["fetch_status", "http_status", "text", "n_chars", "meta_date", "error"]
    values = [result.get(f) for f in fields]
    with db:
        db.execute(
            f"UPDATE bodies SET {', '.join(f + '=?' for f in fields)}, fetched_at=? WHERE gnews_url=?",
            (*values, now(), url),
        )


def pending_fetch(
    db: sqlite3.Connection, pilot_only: bool, limit: int | None
) -> list[tuple[str, str, str]]:
    query = (
        "SELECT gnews_url, decoded_url, domain FROM bodies"
        " WHERE dup_of IS NULL AND decode_status = 'ok' AND fetch_status IS NULL"
    )
    if pilot_only:
        query += " AND pilot = 1"
    query += " ORDER BY priority, published_at DESC"
    if limit:
        query += f" LIMIT {int(limit)}"
    return list(db.execute(query))


async def fetch_all(
    db: sqlite3.Connection,
    pilot_only: bool = False,
    limit: int | None = None,
    concurrency: int = 8,
    min_interval: float = 2.0,
    transport=None,
) -> int:
    import httpx

    todo = pending_fetch(db, pilot_only, limit)
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9"}
    async with httpx.AsyncClient(headers=headers, timeout=30.0, transport=transport) as client:
        robots, pacer = Robots(client), DomainPacer(min_interval)
        done = 0
        # Uma fila por site: com uma fila única, vários trabalhadores ficavam parados esperando a
        # vez no mesmo site. Sites com mais notícias começam primeiro, porque definem o tempo total.
        by_domain = by_domain_largest_first(todo)
        slots = asyncio.Semaphore(concurrency)

        async def drain(domain: str, items: list[tuple[str, str]]):
            nonlocal done
            async with slots:
                for gnews_url, url in items:
                    save_fetched(db, gnews_url, await fetch_one(client, robots, pacer, url, domain))
                    done += 1
                    if done % 100 == 0:
                        logger.warning("baixados %d de %d", done, len(todo))

        await asyncio.gather(*(drain(d, items) for d, items in by_domain))
    return done


def by_domain_largest_first(todo) -> list[tuple[str, list[tuple[str, str]]]]:
    groups: dict[str, list[tuple[str, str]]] = {}
    for gnews_url, url, domain in todo:
        groups.setdefault(domain, []).append((gnews_url, url))
    return sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def report(db: sqlite3.Connection, pilot_only: bool, review_path: Path, n_review: int = 30) -> str:
    where = "WHERE dup_of IS NULL" + (" AND pilot = 1" if pilot_only else "")
    df = pd.read_sql(f"SELECT * FROM bodies {where}", db)
    lines = [f"notícias: {len(df)}"]
    lines.append(
        "decodificação: "
        + df.decode_status.fillna("pendente").value_counts().to_string().replace("\n", "; ")
    )
    fetched = df[df.decode_status == "ok"]
    lines.append(
        "download: "
        + fetched.fetch_status.fillna("pendente").value_counts().to_string().replace("\n", "; ")
    )
    ok = fetched[fetched.fetch_status == "ok"]
    if len(ok):
        lines.append(
            f"caracteres (ok): mediana {ok.n_chars.median():.0f}, p10 {ok.n_chars.quantile(0.1):.0f}"
        )
        same_day = (ok.meta_date.notna()) & (ok.meta_date == ok.published_at.str[:10])
        lines.append(
            f"data do metadado = data do Google: {same_day.sum()} de {ok.meta_date.notna().sum()}"
        )
    by_domain = fetched.groupby("domain").fetch_status.agg(
        total="size", ok=lambda s: (s == "ok").sum(), status=lambda s: s.value_counts().idxmax()
    )
    lines.append(
        "sites com mais notícias:\n"
        + by_domain.sort_values("total", ascending=False).head(25).to_string()
    )
    text = "\n".join(lines)

    sample = ok.sample(min(n_review, len(ok)), random_state=0) if len(ok) else ok
    with open(review_path, "w", encoding="utf-8") as f:
        for r in sample.itertuples():
            f.write(
                f"## {strip_source(r.title)}\n{r.domain} | {r.published_at[:10]} | {r.n_chars} chars\n\n"
            )
            f.write(f"INÍCIO: {r.text[:700]}\n\n[...]\n\nFIM: {r.text[-400:]}\n\n---\n\n")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    p = sub.add_parser("decode")
    p.add_argument("--pilot", type=int, help="marca e decodifica só uma amostra de N notícias")
    p.add_argument("--limit", type=int)
    p.add_argument("--interval", type=float, default=1.0, help="segundos entre páginas do Google")
    p.add_argument("--batch-size", type=int, default=10)
    p = sub.add_parser("fetch")
    p.add_argument(
        "--all", action="store_true", help="além do piloto, baixa todas as decodificadas"
    )
    p.add_argument("--limit", type=int)
    p.add_argument("--concurrency", type=int, default=16, help="sites baixados em paralelo")
    p.add_argument(
        "--min-interval", type=float, default=2.0, help="segundos entre pedidos ao mesmo site"
    )
    p = sub.add_parser("report")
    p.add_argument("--all", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s")
    db = connect(args.db)
    if args.cmd == "init":
        added = init(db, [load_live(), load_backfill_env()])
        total, dups = db.execute("SELECT count(*), count(dup_of) FROM bodies").fetchone()
        print(f"{added} novas; {total} no total, {dups} duplicatas que não serão baixadas")
    elif args.cmd == "decode":
        pilot_only = args.pilot is not None
        if pilot_only:
            print(f"piloto: {mark_pilot(db, args.pilot)} notícias marcadas")
        client, batch = google_decoder(args.interval)
        with client:
            done, total = decode(db, batch, pilot_only, args.limit, args.batch_size)
        print(f"decodificadas {done} de {total}")
    elif args.cmd == "fetch":
        done = asyncio.run(
            fetch_all(db, not args.all, args.limit, args.concurrency, args.min_interval)
        )
        print(f"baixadas {done}")
    elif args.cmd == "report":
        review = NEWS_DIR / ("review_all.md" if args.all else "pilot_review.md")
        print(report(db, not args.all, review))
        print(f"amostra para revisão: {review}")


if __name__ == "__main__":
    main()
