# fetch_news — B3 Stock News Downloader

Downloads **all** announcements published by a Brazilian company on B3's
*Plantão de Notícias* as plain **Markdown text**.

PDFs are fetched from CVM, converted to Markdown with
[docling](https://github.com/DS4SD/docling), and cached on disk so repeated
runs are instant.

> **Other branches**
> - [`main`](../../tree/main) — research comparing workflow vs agent approaches for fundamental analysis
> - [`paper/iclr-2026-workshop`](../../tree/paper/iclr-2026-workshop) — code used to produce the ICLR 2026 Workshop paper

---

## What types of news are included?

Everything B3 publishes for the company, for example:

| Category | Portuguese label |
|---|---|
| Material fact | Fato Relevante |
| Earnings release | Comunicado ao Mercado |
| Notice to shareholders | Aviso aos Acionistas |
| AGM / EGM call | Edital de Convocação |
| Management report | Relatório da Administração |
| And more… | … |

This is different from the `fetch_material_facts` function in
`src/tools/material_facts.py`, which only returns items whose title contains
"Fato Relevante".

> **Historical data beyond 365 days**: B3's Plantão de Notícias API only covers
> the last ~365 days. For older documents, use `fetch_material_facts_from_ipe`
> (also in `src/tools/material_facts.py`), which pulls data from the
> [CVM IPE open-data portal](https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/)
> and covers disclosures back to 2003.

---

## Setup

### 1. Install dependencies

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
uv sync
```

### 2. (Optional) GPU acceleration for docling

docling uses deep-learning models for PDF parsing. On machines with a CUDA
GPU you can speed things up:

```bash
uv add docling[gpu]
```

---

## Running the script

```
uv run fetch_news.py --ticker <TICKER> --start <YYYY-MM> --end <YYYY-MM> [--output <DIR>]
```

### Arguments

| Argument | Required | Description |
|---|---|---|
| `--ticker` | yes | B3 ticker, e.g. `PETR4`, `VALE3`, `ELET3` |
| `--start` | yes | First month to fetch, format `YYYY-MM` |
| `--end` | yes | Last month to fetch, format `YYYY-MM` (inclusive) |
| `--output` | no | Output folder (default: `data/news/<ticker>`) |

### Examples

Fetch all news for Petrobras in Q1 2025:

```bash
uv run fetch_news.py --ticker PETR4 --start 2025-01 --end 2025-03
```

Fetch a single month and save to a custom folder:

```bash
uv run fetch_news.py --ticker VALE3 --start 2024-06 --end 2024-06 --output /tmp/vale_news
```

Fetch the whole year for Eletrobras:

```bash
uv run fetch_news.py --ticker ELET3 --start 2024-01 --end 2024-12
```

---

## Output

Each announcement generates **two files** inside the output folder:

```
data/news/<ticker>/
├── <noticia_id>.pdf    # original PDF from CVM
└── <noticia_id>.md     # Markdown conversion (used by downstream code)
```

The `.md` file is what you want to read or feed into an LLM.  Its filename is
the internal B3 news ID, which is also embedded in the `url` field of each
result.

If a `.md` file already exists the script skips the download and conversion
steps, so it is safe to re-run.

---

## Using fetch_news as a Python function

You can also call `fetch_news` directly from Python:

```python
from fetch_news import fetch_news

news = fetch_news(ticker="PETR4", year=2025, month=3)

for item in news:
    print(item["data_hora"], item["titulo"])
    print(item["conteudo"][:500])   # first 500 chars of the Markdown
    print("---")
```

Each item in the returned list is a `dict` with these keys:

| Key | Type | Description |
|---|---|---|
| `titulo` | `str` | Announcement category / type |
| `headline` | `str` | Short headline |
| `data_hora` | `datetime` | Publication timestamp |
| `conteudo` | `str` | Full text in Markdown |
| `url` | `str` | B3 detail page URL |

---

## How it works

### `fetch_news` / `fetch_material_facts` — B3 Plantão de Notícias

```
B3 Plantão de Notícias API
        │
        │  (list of announcements for the period)
        ▼
Filter by ticker root (e.g. "PETR" matches PETR3, PETR4, PETR8)
        │
        ▼
B3 detail page  ──►  extract CVM PDF link
        │
        ▼
CVM ExibirPDF API  ──►  base64-encoded PDF
        │
        ▼
docling DocumentConverter  ──►  Markdown text
        │
        ▼
Cache to disk  (.pdf + .md)
```

1. **List**: [`finbr`](https://pypi.org/project/finbr/)'s `plantao_noticias.get` retrieves
   all announcements for the requested period from B3.
2. **Filter**: items whose ticker does not start with the root of the requested
   ticker are dropped (e.g. fetching `PETR4` will also return `PETR3` news
   because they are the same company).
3. **PDF URL**: the B3 detail page is parsed to find the CVM document link.
4. **Download**: the PDF is fetched from CVM's internal `ExibirPDF` endpoint,
   which returns the file as a base64-encoded JSON payload.
5. **Convert**: docling converts the PDF to Markdown, preserving tables and
   structure as much as possible.
6. **Cache**: the `.pdf` and `.md` files are written once and reused on
   subsequent runs.

**Limitation**: covers only the last ~365 days.

---

### `fetch_material_facts_from_ipe` — CVM IPE Open Data

For historical data beyond the 365-day B3 window, `fetch_material_facts_from_ipe`
(in `src/tools/material_facts.py`) uses the CVM IPE open-data portal.

```
CVM IPE yearly ZIP  (ipe_cia_aberta_{year}.zip)
        │
        │  cached in data/ipe_cache/
        ▼
Filter rows by CNPJ + month
        │
        ▼
CVM ENET document page  ──►  PDF download
        │
        ▼
docling DocumentConverter  ──►  Markdown text
        │
        ▼
Cache to disk  (data/material_facts/<ticker>/<protocolo>.md)
```

1. **Download ZIP**: the full IPE index for the requested year is downloaded once
   and cached at `data/ipe_cache/ipe_cia_aberta_{year}.zip`.
2. **Filter**: rows are matched by normalised CNPJ and target month prefix — all
   document categories are included.
3. **Fetch PDF**: each matching row's `Link_Download` is used to derive the ENET
   document URL, from which the PDF is downloaded.
4. **Convert & cache**: same docling pipeline as above; `.md` files are reused
   on subsequent runs.

#### Fallback chain used by the investment-house pipeline

`src/experiments/manager/material_facts_report.py` tries sources in order:

```
fetch_material_facts_from_ipe  (CVM IPE — full history)
        │  no results?
        ▼
fetch_material_facts            (B3 Plantão — last ~365 days)
        │  no results?
        ▼
"Sem comunicados divulgados neste mês."
```
