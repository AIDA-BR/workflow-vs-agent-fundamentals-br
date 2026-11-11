import asyncio
import json
import sys
from pathlib import Path

import httpx
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fetch_bodies as fb  # noqa: E402


def frame(rows, kind="ticker", origem="live"):
    df = pd.DataFrame(rows, columns=["gnews_url", "ticker", "title", "source", "published_at"])
    return df.assign(kind=kind, origem=origem)


def test_strip_source_remove_o_sufixo_do_google():
    assert fb.strip_source("Vale (VALE3) sobe 3% - InfoMoney") == "Vale (VALE3) sobe 3%"
    assert fb.strip_source("Sem sufixo") == "Sem sufixo"


def test_duplicata_por_titulo_e_fonte_aponta_para_o_canonico():
    live = frame(
        [
            (
                "g1",
                "PETR4",
                "Ibama multa Petrobras - Estadão",
                "Estadão",
                "2026-06-01T10:00:00+00:00",
            ),
            (
                "g2",
                "PETR3",
                "Ibama multa Petrobras! - Estadão",
                "Estadão",
                "2026-06-01T11:00:00+00:00",
            ),
            ("g3", "PETR4", "Ibama multa Petrobras - Valor", "Valor", "2026-06-01T12:00:00+00:00"),
        ]
    )
    df = fb.build_candidates([live]).set_index("gnews_url")
    assert df.loc["g2", "dup_of"] == "g1"
    assert pd.isna(df.loc["g1", "dup_of"]) and pd.isna(df.loc["g3", "dup_of"])


def test_mesmo_link_na_busca_ambiental_e_na_live_fica_como_ambiental():
    live = frame([("g1", "VALE3", "Vale multada", "X", "2026-06-01T10:00:00+00:00")])
    env = frame(
        [("g1", "VALE3", "Vale multada", "X", "2026-06-01T10:00:00+00:00")], "env", "backfill"
    )
    df = fb.build_candidates([live, env])
    assert len(df) == 1 and df.kind[0] == "env" and df.priority[0] == 0


def test_prioridade():
    df = fb.build_candidates(
        [
            frame(
                [("a", "VALE3", "t1", "X", "2026-06-01"), ("b", "ITUB4", "t2", "X", "2026-06-01")]
            ),
            frame([("c", "ITUB4", "t3", "X", "2026-06-01")], "env", "backfill"),
        ]
    ).set_index("gnews_url")
    assert (df.loc["c", "priority"], df.loc["a", "priority"], df.loc["b", "priority"]) == (0, 1, 2)


def test_init_e_idempotente():
    db = fb.connect(":memory:")
    live = frame([("g1", "VALE3", "t", "X", "2026-06-01")])
    assert fb.init(db, [live]) == 1
    assert fb.init(db, [live]) == 0


def test_piloto_cobre_varias_fontes_e_respeita_o_tamanho():
    df = pd.DataFrame(
        {
            "gnews_url": [f"u{i}" for i in range(300)],
            "source": ["A"] * 200 + ["B"] * 90 + ["C"] * 10,
        }
    )
    picked = fb.pilot_sample(df, 50)
    sources = df.set_index("gnews_url").loc[picked, "source"]
    assert len(picked) == 50 and len(set(picked)) == 50
    assert set(sources) == {"A", "B", "C"}
    assert sources.value_counts()["A"] > sources.value_counts()["C"]


def seeded_db(n=3):
    db = fb.connect(":memory:")
    rows = [(f"g{i}", "VALE3", f"t{i}", "X", f"2026-06-0{i + 1}") for i in range(n)]
    fb.init(db, [frame(rows)])
    return db


def test_decode_grava_sucesso_e_falha():
    db = seeded_db(2)

    def batch(urls):
        return [
            {"success": True, "decoded_url": "https://Site.com.br/a"},
            {"success": False, "message": "x"},
        ]

    done, total = fb.decode(db, batch, sleep=lambda _: None)
    rows = dict(db.execute("SELECT gnews_url, decode_status FROM bodies"))
    assert (done, total) == (1, 2)
    assert sorted(rows.values()) == ["failed", "ok"]
    assert (
        db.execute("SELECT domain FROM bodies WHERE decode_status='ok'").fetchone()[0]
        == "site.com.br"
    )


def test_decode_lote_bloqueado_nao_grava_e_para():
    db = seeded_db(3)
    waits = []
    fb.decode(db, lambda urls: [{"success": False, "message": "429"}] * len(urls),
              batch_size=1, sleep=waits.append, max_failed_batches=2)  # fmt: skip
    assert (
        db.execute("SELECT count(*) FROM bodies WHERE decode_status IS NOT NULL").fetchone()[0] == 0
    )
    assert waits == [60, 120]


def test_classify():
    assert fb.classify(None)[0] == "empty"
    assert fb.classify(json.dumps({"text": "curto"}))[0] == "short"
    status, text, n, date = fb.classify(json.dumps({"text": "x" * 600, "date": "2026-06-01"}))
    assert (status, n, date) == ("ok", 600, "2026-06-01")


ARTICLE = (
    "<html><body><article><h1>Título</h1>"
    + "<p>"
    + "Texto da notícia. " * 60
    + "</p></article></body></html>"
)


def run_fetch(handler, min_chars_text=ARTICLE):
    db = seeded_db(2)
    with db:
        db.execute(
            "UPDATE bodies SET decode_status='ok', decoded_url='https://a.com/x', domain='a.com' WHERE gnews_url='g0'"
        )
        db.execute(
            "UPDATE bodies SET decode_status='ok', decoded_url='https://b.com/y', domain='b.com' WHERE gnews_url='g1'"
        )
    asyncio.run(
        fb.fetch_all(db, pilot_only=False, min_interval=0, transport=httpx.MockTransport(handler))
    )
    return dict(db.execute("SELECT domain, fetch_status FROM bodies"))


def test_fetch_respeita_robots_e_extrai_texto():
    def handler(request):
        if request.url.path == "/robots.txt":
            body = "User-agent: *\nDisallow: /" if request.url.host == "b.com" else ""
            return httpx.Response(200, text=body)
        return httpx.Response(200, text=ARTICLE, headers={"content-type": "text/html"})

    assert run_fetch(handler) == {"a.com": "ok", "b.com": "robots"}


def test_fetch_robots_404_libera_e_erro_http_vira_status():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.host == "b.com":
            return httpx.Response(403)
        return httpx.Response(200, text=ARTICLE, headers={"content-type": "text/html"})

    assert run_fetch(handler) == {"a.com": "ok", "b.com": "http"}


def test_fetch_robots_inacessivel_bloqueia_o_site():
    def handler(request):
        if request.url.path == "/robots.txt" and request.url.host == "b.com":
            raise httpx.ConnectError("sem rede")
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=ARTICLE, headers={"content-type": "text/html"})

    assert run_fetch(handler)["b.com"] == "robots"
