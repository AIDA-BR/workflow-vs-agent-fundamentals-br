import calendar
import os
import re
import urllib3

import requests
from bs4 import BeautifulSoup
from docling.document_converter import DocumentConverter
from finbr.b3 import plantao_noticias

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_OUTPUT_FOLDER = "data/material_facts"


def _extract_noticia_id(url: str) -> str | None:
    match = re.search(r"idNoticia=(\d+)", url)
    return match.group(1) if match else None


def _get_pdf_url_from_detail_page(detail_url: str) -> str | None:
    """Fetch the B3 news detail page and return the CVM PDF link."""
    try:
        r = requests.get(detail_url, verify=False, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            if "Clique aqui" in text or "documento na íntegra" in text:
                href = a["href"]
                return href if href.startswith("http") else f"https:{href}"
        return None
    except Exception:
        return None


def _download_pdf(pdf_url: str, pdf_path: str) -> bool:
    """Download a PDF from CVM and save it to pdf_path. Returns True on success."""
    try:
        r = requests.get(pdf_url, verify=False, timeout=60, stream=True)
        r.raise_for_status()
        with open(pdf_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
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
