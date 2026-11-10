"""Backfill local de notícias via Google News RSS, para meses anteriores à coleta de produção.

Grava apenas em um SQLite local (``data/news/backfill.sqlite``); não toca na produção.

Dois tipos de busca por empresa:

* ``ticker``: a mesma busca do job de produção (``q=PETR4``), para os dados serem comparáveis;
* ``env``: nome da empresa + termos ambientais, porque notícia ambiental costuma citar "Vale" e
  não "VALE3".

Cada consulta devolve no máximo ~100 itens, então a janela (uma semana) é dividida ao meio sempre
que a resposta vem cheia. O progresso é salvo por janela: rodar de novo continua de onde parou.

    qlib_baseline/.venv/bin/python news_signal/backfill_news.py --newest 2026-04 --oldest 2025-11

Para o teste de qualidade contra a coleta ao vivo, use outro banco e desligue a parada:

    ... --newest 2026-10 --oldest 2026-05 --db data/news/backfill_recall.sqlite --no-stop
"""

import argparse
import csv
import http.client
import logging
import random
import sqlite3
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Iterator, Sequence

logger = logging.getLogger("backfill_news")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "data" / "news" / "backfill.sqlite"

FEED_URL = "https://news.google.com/rss/search?q={query}&hl=pt-BR&gl=BR&ceid=BR:pt"
USER_AGENT = "news-signal-research/0.1"
#: A partir daqui a resposta é tratada como cheia e a janela é dividida.
FULL_RESPONSE = 95
WINDOW_DAYS = 7

KINDS = ("ticker", "env")
ENV_TERMS = (
    "ambiental",
    "meio ambiente",
    "ESG",
    "IBAMA",
    "barragem",
    "desmatamento",
    "vazamento",
    "emissões",
    "carbono",
    "licenciamento",
    "crise hídrica",
)

#: As 9 ações do paper, com o nome usado nas buscas ambientais.
PAPER_STOCKS = (
    ("ALUP11", "Alupar"),
    ("AURE3", "Auren"),
    ("CPLE3", "Copel"),
    ("EALT4", "Electro Aço Altona"),
    ("ENEV3", "Eneva"),
    ("EQTL3", "Equatorial Energia"),
    ("PETR4", "Petrobras"),
    ("RECV3", "PetroReconcavo"),
    ("VALE3", "Vale"),
)


class FeedBlocked(RuntimeError):
    """O servidor continuou recusando as requisições depois de todas as tentativas."""


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    published_at: datetime
    source: str


def env_query(name: str) -> str:
    terms = " OR ".join(f'"{t}"' if " " in t else t for t in ENV_TERMS)
    return f'"{name}" ({terms})'


def query_for(kind: str, ticker: str, name: str) -> str:
    if kind == "ticker":
        return ticker
    if kind == "env":
        return env_query(name)
    raise ValueError(f"tipo de busca desconhecido: {kind}")


def feed_url(query: str, start: date, end: date) -> str:
    """URL da janela [start, end).

    A inclusão das datas em ``after:``/``before:`` não é documentada, então a consulta sobra um dia
    de cada lado e ``collect_window`` recorta pela data de publicação.
    """
    after = (start - timedelta(days=1)).isoformat()
    before = (end + timedelta(days=1)).isoformat()
    full = f"{query} after:{after} before:{before}"
    return FEED_URL.format(query=urllib.parse.quote(full))


def parse_feed(xml_bytes: bytes) -> list[Article]:
    """Itens do RSS; item sem link ou sem data válida é descartado (como no job de produção)."""
    articles = []
    for item in ET.fromstring(xml_bytes).iter("item"):
        url = (item.findtext("link") or "").strip()
        title = (item.findtext("title") or "").strip()
        raw_date = item.findtext("pubDate")
        if not url or not raw_date:
            continue
        try:
            published = parsedate_to_datetime(raw_date)
        except (TypeError, ValueError):
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        source = (item.findtext("source") or "Google News").strip()
        articles.append(Article(title, url, published.astimezone(timezone.utc), source))
    return articles


class Fetcher:
    """GET com intervalo mínimo entre requisições e backoff exponencial em 429/5xx."""

    def __init__(
        self,
        min_interval: float = 3.0,
        max_retries: int = 5,
        opener: Callable[[str], bytes] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.opener = opener or self._open
        self.sleep = sleep
        self._last = 0.0

    @staticmethod
    def _open(url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()

    def _pace(self) -> None:
        wait = self._last + self.min_interval - time.monotonic()
        if wait > 0:
            self.sleep(wait + random.uniform(0, self.min_interval / 3))
        self._last = time.monotonic()

    def get(self, url: str) -> bytes:
        for attempt in range(self.max_retries + 1):
            self._pace()
            try:
                return self.opener(url)
            except urllib.error.HTTPError as exc:
                if exc.code != 429 and exc.code < 500:
                    raise
                reason = f"HTTP {exc.code}"
            except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
                # inclui RemoteDisconnected, ConnectionResetError e timeouts
                reason = f"{type(exc).__name__}: {exc}"
            if attempt < self.max_retries:
                delay = 30 * 2**attempt
                logger.warning("%s; nova tentativa em %ds", reason, delay)
                self.sleep(delay)
        raise FeedBlocked(f"desisti depois de {self.max_retries + 1} tentativas: {reason}")


class Store:
    def __init__(self, path: Path | str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS articles (
                url TEXT NOT NULL,
                ticker TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                published_at TEXT NOT NULL,
                source TEXT NOT NULL,
                origem TEXT NOT NULL DEFAULT 'backfill',
                collected_at TEXT NOT NULL,
                PRIMARY KEY (url, ticker, kind)
            );
            CREATE TABLE IF NOT EXISTS windows (
                ticker TEXT NOT NULL,
                kind TEXT NOT NULL,
                start TEXT NOT NULL,
                end TEXT NOT NULL,
                n_items INTEGER NOT NULL,
                truncated INTEGER NOT NULL,
                PRIMARY KEY (ticker, kind, start, end)
            );
            """
        )

    def is_done(self, ticker: str, kind: str, start: date, end: date) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM windows WHERE ticker=? AND kind=? AND start=? AND end=?",
            (ticker, kind, start.isoformat(), end.isoformat()),
        ).fetchone()
        return row is not None

    def save(
        self,
        ticker: str,
        kind: str,
        start: date,
        end: date,
        articles: Sequence[Article],
        n_items: int,
        truncated: bool,
    ) -> None:
        """Grava os artigos e marca a janela como concluída na mesma transação."""
        now = datetime.now(timezone.utc).isoformat()
        with self.db:
            self.db.executemany(
                "INSERT OR IGNORE INTO articles (url, ticker, kind, title, published_at, source,"
                " collected_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (a.url, ticker, kind, a.title, a.published_at.isoformat(), a.source, now)
                    for a in articles
                ],
            )
            self.db.execute(
                "INSERT OR REPLACE INTO windows VALUES (?, ?, ?, ?, ?, ?)",
                (ticker, kind, start.isoformat(), end.isoformat(), n_items, int(truncated)),
            )

    def count(self, start: date, end: date) -> int:
        row = self.db.execute(
            "SELECT count(*) FROM articles WHERE published_at >= ? AND published_at < ?",
            (start.isoformat(), end.isoformat()),
        ).fetchone()
        return row[0]


def collect_window(
    store: Store, fetcher: Fetcher, ticker: str, kind: str, query: str, start: date, end: date
) -> None:
    if store.is_done(ticker, kind, start, end):
        return
    items = parse_feed(fetcher.get(feed_url(query, start, end)))
    span = (end - start).days
    if len(items) >= FULL_RESPONSE and span > 1:
        middle = start + timedelta(days=span // 2)
        collect_window(store, fetcher, ticker, kind, query, start, middle)
        collect_window(store, fetcher, ticker, kind, query, middle, end)
        store.save(ticker, kind, start, end, [], len(items), False)
        return
    inside = [a for a in items if start <= a.published_at.date() < end]
    truncated = len(items) >= FULL_RESPONSE
    if truncated:
        logger.warning("%s/%s %s: dia com resposta cheia, pode faltar notícia", ticker, kind, start)
    store.save(ticker, kind, start, end, inside, len(items), truncated)


def parse_month(text: str) -> date:
    return datetime.strptime(text, "%Y-%m").date().replace(day=1)


def next_month(month: date) -> date:
    return (month.replace(day=28) + timedelta(days=4)).replace(day=1)


def previous_month(month: date) -> date:
    return (month - timedelta(days=1)).replace(day=1)


def months_backward(newest: date, oldest: date) -> Iterator[date]:
    month = newest
    while month >= oldest:
        yield month
        month = previous_month(month)


def windows_of(month: date, days: int = WINDOW_DAYS) -> Iterator[tuple[date, date]]:
    start, stop = month, next_month(month)
    while start < stop:
        end = min(start + timedelta(days=days), stop)
        yield start, end
        start = end


def should_stop(counts_newest_first: Sequence[int], ratio: float = 0.2) -> bool:
    """True se o mês mais antigo já coletado despencou em relação aos mais recentes."""
    if len(counts_newest_first) < 2:
        return False
    return counts_newest_first[-1] < ratio * statistics.median(counts_newest_first[:-1])


def run(
    store: Store,
    fetcher: Fetcher,
    stocks: Sequence[tuple[str, str]],
    newest: date,
    oldest: date,
    kinds: Sequence[str] = KINDS,
    stop_on_drop: bool = True,
) -> list[tuple[date, int]]:
    """Recua mês a mês e devolve (mês, artigos), do mais recente para o mais antigo."""
    summary: list[tuple[date, int]] = []
    for month in months_backward(newest, oldest):
        for ticker, name in stocks:
            for kind in kinds:
                query = query_for(kind, ticker, name)
                for start, end in windows_of(month):
                    collect_window(store, fetcher, ticker, kind, query, start, end)
        count = store.count(month, next_month(month))
        summary.append((month, count))
        logger.warning("%s: %d artigos", month.strftime("%Y-%m"), count)
        if stop_on_drop and should_stop([c for _, c in summary]):
            logger.warning("Volume despencou em %s: parando o recuo.", month.strftime("%Y-%m"))
            break
    return summary


def read_stocks(path: Path) -> list[tuple[str, str]]:
    """CSV com colunas ``ticker`` e ``name``."""
    with open(path, newline="", encoding="utf-8") as f:
        return [(row["ticker"].strip().upper(), row["name"].strip()) for row in csv.DictReader(f)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--newest", default="2026-04", help="mês mais recente (AAAA-MM)")
    parser.add_argument("--oldest", default="2025-11", help="mês mais antigo (AAAA-MM)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--tickers-file", type=Path, help="CSV ticker,name; padrão: 9 ações do paper"
    )
    parser.add_argument("--kinds", nargs="+", choices=KINDS, default=list(KINDS))
    parser.add_argument(
        "--min-interval", type=float, default=3.0, help="segundos entre requisições"
    )
    parser.add_argument("--no-stop", action="store_true", help="não para se o volume despencar")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s")
    stocks = read_stocks(args.tickers_file) if args.tickers_file else list(PAPER_STOCKS)
    try:
        summary = run(
            Store(args.db),
            Fetcher(min_interval=args.min_interval),
            stocks,
            parse_month(args.newest),
            parse_month(args.oldest),
            args.kinds,
            stop_on_drop=not args.no_stop,
        )
    except FeedBlocked as exc:
        raise SystemExit(f"Interrompido, progresso salvo em {args.db}. {exc}")
    for month, count in summary:
        print(f"{month:%Y-%m}\t{count}")


if __name__ == "__main__":
    main()
