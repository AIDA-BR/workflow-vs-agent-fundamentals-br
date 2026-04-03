import base64
import calendar
import json
import os
import re
import urllib3

import requests
from bs4 import BeautifulSoup
from docling.document_converter import DocumentConverter
from finbr.b3 import plantao_noticias

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_OUTPUT_FOLDER = "data/material_facts"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    )
}


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
        # get_text() decodes HTML entities, so &amp;flnk → &flnk
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
    """Convert a PDF file to markdown text using docling."""
    converter = DocumentConverter()
    result = converter.convert(pdf_path)
    return result.document.export_to_markdown()


def fetch_material_facts(
    ticker: str,
    year: int,
    month: int,
    output_folder: str | None = None,
) -> list[dict]:
    """
    Fetch "Fato Relevante" B3 announcements for a given ticker and month.

    Downloads PDFs from CVM, converts them to markdown with docling, and caches
    results to disk. Skips files already present in output_folder.

    Returns a list of dicts with keys: titulo, headline, data_hora, conteudo, url.
    Returns [] on empty result or unrecoverable error.
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
    except Exception:
        return []

    results = []
    for n in noticias:
        # Match all share classes of the same company (e.g. ELET3 and ELET6)
        if not n.ticker.startswith(ticker_root):
            continue
        # Only "Fato Relevante" announcements
        if "Fato Relevante" not in (n.titulo or "") and "Fato Relevante" not in (n.headline or ""):
            continue

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
            except Exception:
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


if __name__ == "__main__":
    fetch_material_facts(ticker="PETR", year=2026, month=3, output_folder="facts/")
