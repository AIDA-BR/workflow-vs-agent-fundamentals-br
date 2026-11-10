import http.client
import sys
import urllib.error
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backfill_news as bn  # noqa: E402


def rss(items):
    body = "".join(
        f"<item><title>{escape(title)}</title><link>{escape(url)}</link>"
        f"<pubDate>{format_datetime(when)}</pubDate><source url='x'>Fonte</source></item>"
        for title, url, when in items
    )
    return f"<rss><channel>{body}</channel></rss>".encode()


def at(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc)


def dates_in(url: str) -> tuple[date, date]:
    query = urllib.parse.unquote(url)
    after = query.split("after:")[1][:10]
    before = query.split("before:")[1][:10]
    return date.fromisoformat(after) + timedelta(days=1), date.fromisoformat(before) - timedelta(
        days=1
    )


class FakeGoogle:
    """Devolve um item por dia da janela, mais `extra` itens no primeiro dia."""

    def __init__(self, extra=0):
        self.extra = extra
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        start, end = dates_in(url)
        days = [start + timedelta(days=i) for i in range((end - start).days)]
        items = [("t", f"u{d}", at(d)) for d in days]
        items.append(("t", f"fora{start}", at(start - timedelta(days=1))))
        if len(days) > 1:
            items += [("t", f"x{start}{i}", at(start)) for i in range(self.extra)]
        return rss(items)


def fetcher(opener):
    return bn.Fetcher(min_interval=0, opener=opener, sleep=lambda _: None)


def test_parse_feed_descarta_item_sem_data_e_converte_para_utc():
    xml = (
        b"<rss><channel>"
        b"<item><title>A</title><link>u1</link><pubDate>Mon, 03 Nov 2025 21:00:00 -0300</pubDate></item>"
        b"<item><title>B</title><link>u2</link></item>"
        b"</channel></rss>"
    )
    articles = bn.parse_feed(xml)
    assert [a.url for a in articles] == ["u1"]
    assert articles[0].published_at == datetime(2025, 11, 4, 0, 0, tzinfo=timezone.utc)
    assert articles[0].source == "Google News"


def test_feed_url_sobra_um_dia_de_cada_lado():
    query = urllib.parse.unquote(bn.feed_url("PETR4", date(2025, 11, 8), date(2025, 11, 15)))
    assert "PETR4 after:2025-11-07 before:2025-11-16" in query


def test_env_query_usa_nome_e_aspas_em_termos_compostos():
    query = bn.env_query("Vale")
    assert query.startswith('"Vale" (')
    assert '"meio ambiente"' in query and " OR IBAMA OR " in query


def test_janela_descarta_o_que_esta_fora_do_intervalo():
    store = bn.Store(":memory:")
    bn.collect_window(
        store,
        fetcher(FakeGoogle()),
        "PETR4",
        "ticker",
        "PETR4",
        date(2025, 11, 1),
        date(2025, 11, 8),
    )
    urls = {r[0] for r in store.db.execute("SELECT url FROM articles")}
    assert urls == {f"u{date(2025, 11, d)}" for d in range(1, 8)}


def test_resposta_cheia_divide_a_janela():
    google = FakeGoogle(extra=bn.FULL_RESPONSE)
    store = bn.Store(":memory:")
    bn.collect_window(
        store, fetcher(google), "PETR4", "ticker", "PETR4", date(2025, 11, 1), date(2025, 11, 8)
    )
    assert len(google.calls) > 1
    assert store.is_done("PETR4", "ticker", date(2025, 11, 1), date(2025, 11, 4))
    assert store.count(date(2025, 11, 7), date(2025, 11, 8)) == 1


def test_rodar_de_novo_nao_refaz_janela_concluida():
    google = FakeGoogle()
    store = bn.Store(":memory:")
    for _ in range(2):
        bn.collect_window(
            store, fetcher(google), "PETR4", "ticker", "PETR4", date(2025, 11, 1), date(2025, 11, 8)
        )
    assert len(google.calls) == 1


def test_mesma_url_fica_em_duas_empresas():
    store = bn.Store(":memory:")
    google = FakeGoogle()
    for ticker in ("PETR4", "VALE3"):
        bn.collect_window(
            store, fetcher(google), ticker, "ticker", ticker, date(2025, 11, 1), date(2025, 11, 8)
        )
    rows = store.db.execute("SELECT count(DISTINCT ticker) FROM articles").fetchone()[0]
    assert rows == 2


def test_windows_cobrem_o_mes_sem_buracos():
    windows = list(bn.windows_of(date(2026, 2, 1)))
    assert windows[0][0] == date(2026, 2, 1) and windows[-1][1] == date(2026, 3, 1)
    assert all(a[1] == b[0] for a, b in zip(windows, windows[1:]))


def test_months_backward_atravessa_o_ano():
    months = list(bn.months_backward(date(2026, 1, 1), date(2025, 11, 1)))
    assert months == [date(2026, 1, 1), date(2025, 12, 1), date(2025, 11, 1)]


@pytest.mark.parametrize(
    "counts,expected",
    [
        ([100], False),
        ([100, 90], False),
        ([100, 90, 10], True),
        ([100, 20], False),
        ([100, 19], True),
    ],
)
def test_should_stop(counts, expected):
    assert bn.should_stop(counts) is expected


def test_run_para_quando_o_volume_despenca():
    calls = {"n": 0}

    def opener(url):
        calls["n"] += 1
        start, _ = dates_in(url)
        n = 20 if start >= date(2026, 3, 1) else 0
        return rss([("t", f"u{start}{i}", at(start)) for i in range(n)])

    summary = bn.run(
        bn.Store(":memory:"), fetcher(opener), [("PETR4", "Petrobras")],
        date(2026, 4, 1), date(2025, 11, 1), kinds=["ticker"],
    )  # fmt: skip
    assert [m for m, _ in summary] == [date(2026, 4, 1), date(2026, 3, 1), date(2026, 2, 1)]


def http_error(code):
    return urllib.error.HTTPError("u", code, "erro", {}, None)


def test_fetcher_tenta_de_novo_em_429():
    answers = [http_error(429), b"ok"]

    def opener(_):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    assert fetcher(opener).get("u") == b"ok"


def test_fetcher_tenta_de_novo_quando_a_conexao_cai():
    answers = [http.client.RemoteDisconnected("caiu"), ConnectionResetError("reset"), b"ok"]

    def opener(_):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    assert fetcher(opener).get("u") == b"ok"


def test_fetcher_desiste_depois_de_bloqueio_persistente():
    def opener(_):
        raise http_error(429)

    with pytest.raises(bn.FeedBlocked):
        bn.Fetcher(min_interval=0, max_retries=2, opener=opener, sleep=lambda _: None).get("u")


def test_fetcher_nao_insiste_em_404():
    calls = []

    def opener(_):
        calls.append(1)
        raise http_error(404)

    with pytest.raises(urllib.error.HTTPError):
        fetcher(opener).get("u")
    assert len(calls) == 1
