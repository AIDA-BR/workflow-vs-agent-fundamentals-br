"""
fetch_news.py — Download B3 news for a stock ticker as text (Markdown).

Fetches all announcements (not just "Fato Relevante") published by a company
on B3's Plantão de Notícias for a given ticker and date range.  PDFs are
downloaded from CVM, converted to Markdown via docling, and cached on disk so
repeated runs are fast.

Usage
-----
    uv run fetch_news.py --ticker PETR4 --start 2025-01 --end 2025-03
    uv run fetch_news.py --ticker VALE3 --start 2024-06 --end 2024-06 --output data/vale_news

Run `uv run fetch_news.py --help` for the full option list.
"""

import argparse
import base64
import calendar
import json
import os
import re
import sys
import urllib3

import requests
from bs4 import BeautifulSoup
from docling.document_converter import DocumentConverter
from finbr.b3 import plantao_noticias

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_OUTPUT_FOLDER = "data/news"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    )
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_noticia_id(url: str) -> str | None:
    match = re.search(r"idNoticia=(\d+)", url)
    return match.group(1) if match else None


def _get_pdf_url_from_detail_page(detail_url: str) -> str | None:
    """Fetch the B3 news detail page and return the CVM PDF link.

    The page is server-side rendered: the content sits in <pre id="conteudoDetalhe">
    and URLs end with ``?flnk`` or ``&flnk`` (HTML-encoded as ``&amp;flnk``).
    JavaScript would normally strip that suffix and create a visible link, so we
    replicate that logic here without needing a browser.
    """
    try:
        r = requests.get(detail_url, headers=_HEADERS, verify=False, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        pre = soup.find("pre", id="conteudoDetalhe")
        if pre is None:
            return None
        text = pre.get_text()
        match = re.search(r"(https?://\S+?)(?:\?flnk|&flnk)", text)
        if match:
            return match.group(1)
        return None
    except Exception:
        return None


def _extract_cvm_id(cvm_url: str) -> str | None:
    match = re.search(r"[?&]ID=(\d+)", cvm_url, re.IGNORECASE)
    return match.group(1) if match else None


def _download_pdf(cvm_url: str, pdf_path: str) -> bool:
    """Download a PDF from CVM via the ExibirPDF API and save to pdf_path.

    CVM does not serve the file at the URL directly — the page POSTs to
    ``frmExibirArquivoIPEExterno.aspx/ExibirPDF`` and receives the PDF as a
    base64-encoded JSON response.  We replicate that call here.
    """
    cvm_id = _extract_cvm_id(cvm_url)
    if cvm_id is None:
        return False
    try:
        payload = json.dumps(
            {"codigoInstituicao": "2", "numeroProtocolo": cvm_id, "token": "", "versaoCaptcha": ""}
        )
        api_url = "https://www.rad.cvm.gov.br/ENET/frmExibirArquivoIPEExterno.aspx/ExibirPDF"
        r = requests.post(
            api_url,
            data=payload,
            headers={**_HEADERS, "Content-Type": "application/json; charset=utf-8"},
            verify=False,
            timeout=60,
        )
        r.raise_for_status()
        d = r.json().get("d", "")
        if not d or d.startswith(":ERRO:") or d == "V2":
            return False
        pdf_bytes = base64.b64decode(d)
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        return True
    except Exception:
        return False


def _pdf_to_markdown(pdf_path: str) -> str:
    """Convert a PDF file to Markdown text using docling."""
    converter = DocumentConverter()
    result = converter.convert(pdf_path)
    return result.document.export_to_markdown()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_news(
    ticker: str,
    year: int,
    month: int,
    output_folder: str | None = None,
) -> list[dict]:
    """Fetch all B3 news for *ticker* published in *year*/*month*.

    Unlike the ``fetch_material_facts`` helper in ``src/tools/material_facts.py``,
    this function does **not** filter by announcement type — every item found on
    B3's Plantão de Notícias for the company is included (earnings releases,
    material facts, notices to shareholders, AGM calls, etc.).

    Downloads PDFs from CVM, converts them to Markdown with docling, and caches
    results to disk.  Skips files already present in *output_folder*.

    Parameters
    ----------
    ticker:
        B3 ticker, e.g. ``"PETR4"`` or ``"VALE3"``.  The last digit is ignored
        so that all share classes of the same company are matched (e.g. ELET3
        and ELET6 are both matched when ``ticker="ELET3"``).
    year, month:
        Calendar year and month to fetch.
    output_folder:
        Directory where PDFs and Markdown files are cached.  Defaults to
        ``data/news/<ticker_root>``.

    Returns
    -------
    list[dict]
        Each item has keys: ``titulo``, ``headline``, ``data_hora``,
        ``conteudo`` (Markdown text), ``url``.
        Returns ``[]`` on empty result or unrecoverable error.
    """
    ticker_root = ticker[:4]
    if output_folder is None:
        output_folder = os.path.join(DEFAULT_OUTPUT_FOLDER, ticker_root)
    os.makedirs(output_folder, exist_ok=True)

    inicio = f"{year}-{month:02d}-01"
    last_day = calendar.monthrange(year, month)[1]
    fim = f"{year}-{month:02d}-{last_day:02d}"

    try:
        noticias = plantao_noticias.get(inicio=inicio, fim=fim)
    except Exception as exc:
        print(f"[fetch_news] Error fetching news list: {exc}", file=sys.stderr)
        return []

    results = []
    for n in noticias:
        # Match all share classes of the same company (e.g. ELET3 and ELET6)
        if not n.ticker.startswith(ticker_root):
            continue
        # NOTE: no type filter here — all announcement types are included.

        noticia_id = _extract_noticia_id(n.url)
        if noticia_id is None:
            continue

        md_path = os.path.join(output_folder, f"{noticia_id}.md")
        pdf_path = os.path.join(output_folder, f"{noticia_id}.pdf")

        if os.path.exists(md_path):
            with open(md_path) as f:
                conteudo = f.read()
        else:
            pdf_url = _get_pdf_url_from_detail_page(n.url)
            if pdf_url is None:
                continue
            if not os.path.exists(pdf_path):
                if not _download_pdf(pdf_url, pdf_path):
                    continue
            try:
                conteudo = _pdf_to_markdown(pdf_path)
            except Exception as exc:
                print(f"[fetch_news] Error converting PDF {pdf_path}: {exc}", file=sys.stderr)
                continue
            with open(md_path, "w") as f:
                f.write(conteudo)

        results.append(
            {
                "titulo": n.titulo,
                "headline": n.headline,
                "data_hora": n.data_hora,
                "conteudo": conteudo,
                "url": n.url,
            }
        )

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_year_month(value: str) -> tuple[int, int]:
    """Parse a YYYY-MM string into (year, month)."""
    try:
        year, month = value.split("-")
        return int(year), int(month)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Expected YYYY-MM, got: {value!r}")


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Download B3 news for a stock ticker as Markdown text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--ticker", required=True, help="B3 ticker, e.g. PETR4")
    parser.add_argument(
        "--start",
        required=True,
        type=_parse_year_month,
        metavar="YYYY-MM",
        help="First month to fetch (inclusive)",
    )
    parser.add_argument(
        "--end",
        required=True,
        type=_parse_year_month,
        metavar="YYYY-MM",
        help="Last month to fetch (inclusive)",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="DIR",
        help=f"Output folder (default: {DEFAULT_OUTPUT_FOLDER}/<ticker>)",
    )
    args = parser.parse_args()

    start_year, start_month = args.start
    end_year, end_month = args.end

    # Enumerate months in [start, end]
    months = []
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1

    all_results = []
    for year, month in months:
        print(f"Fetching {args.ticker} — {year}-{month:02d} …")
        results = fetch_news(
            ticker=args.ticker,
            year=year,
            month=month,
            output_folder=args.output,
        )
        print(f"  {len(results)} news item(s) found.")
        all_results.extend(results)

    print(f"\nTotal: {len(all_results)} news item(s) for {args.ticker}.")
    if all_results:
        folder = args.output or os.path.join(DEFAULT_OUTPUT_FOLDER, args.ticker[:4])
        print(f"Markdown files saved to: {folder}/")


if __name__ == "__main__":
    _main()
