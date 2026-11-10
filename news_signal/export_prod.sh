#!/usr/bin/env bash
# Exporta a tabela stock_news da produção do fin-difusion para data/news/, sem escrever nada lá.
#
#   bash news_signal/export_prod.sh stats    # só agregados → data/news/prod_stats.txt
#   bash news_signal/export_prod.sh export   # linhas → data/news/stock_news_live.csv.gz
#
# Garantias de segurança:
#   * usa `exec -T` no container já em execução (nunca `compose run`, que recria serviços);
#   * a sessão do psql é forçada a somente leitura e tem limite de tempo;
#   * o modo export só roda depois de confirmar que a sessão está em somente leitura.
#
# Variáveis opcionais: PROD_KEY (caminho do .pem), PROD_HOST, PROD_DIR, EXPORT_TIMEOUT_MS.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$REPO_ROOT/data/news"
PROD_KEY="${PROD_KEY:-$HOME/Documents/workspace/fin-difusion/fin-difusion-prod-key.pem}"
PROD_HOST="${PROD_HOST:-ubuntu@15.229.163.191}"
PROD_DIR="${PROD_DIR:-~/fin-difusion}"
EXPORT_TIMEOUT_MS="${EXPORT_TIMEOUT_MS:-300000}"

remote_psql() {
  ssh -i "$PROD_KEY" -o BatchMode=yes -o ConnectTimeout=20 "$PROD_HOST" \
    "cd $PROD_DIR && docker compose -f docker-compose.prod.yml exec -T \
     -e PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=$EXPORT_TIMEOUT_MS' \
     postgres sh -c 'psql -X -q -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -A -F \"|\"'"
}

assert_read_only() {
  local mode
  mode="$(echo "SHOW transaction_read_only;" | remote_psql | sed -n 2p)"
  if [[ "$mode" != "on" ]]; then
    echo "ERRO: a sessão não está em somente leitura (transaction_read_only=$mode). Abortando." >&2
    exit 1
  fi
  echo "Sessão confirmada em somente leitura."
}

stats() {
  remote_psql <<'SQL' | tee "$OUT_DIR/prod_stats.txt"
SELECT pg_size_pretty(pg_total_relation_size('stock_news')) AS tamanho;
SELECT count(*) AS linhas, count(entity_id) AS com_entity, count(DISTINCT ticker) AS tickers,
       count(DISTINCT entity_id) AS entidades, count(DISTINCT source) AS fontes,
       min(created_at) AS min_created, max(created_at) AS max_created,
       min(published_at) AS min_pub, max(published_at) AS max_pub,
       count(*) FILTER (WHERE url LIKE 'https://news.google.com/%') AS url_google
FROM stock_news;
SELECT to_char(published_at, 'YYYY-MM') AS mes_pub, count(*) AS artigos, count(DISTINCT ticker) AS tickers
FROM stock_news GROUP BY 1 ORDER BY 1;
SELECT to_char(created_at, 'YYYY-MM') AS mes_coleta, count(*) AS artigos,
       count(DISTINCT created_at::date) AS dias_com_coleta
FROM stock_news GROUP BY 1 ORDER BY 1;
SELECT ticker, count(*) AS artigos, min(published_at)::date AS primeira
FROM stock_news
WHERE ticker IN ('ALUP11','AURE3','CPLE3','EALT4','ENEV3','EQTL3','PETR4','RECV3','VALE3')
GROUP BY 1 ORDER BY 1;
SELECT percentile_cont(ARRAY[0.1, 0.5, 0.9]) WITHIN GROUP (ORDER BY n) AS p10_p50_p90
FROM (SELECT count(*) AS n FROM stock_news GROUP BY ticker) t;
SELECT left(url, 60) AS exemplo_url FROM stock_news ORDER BY created_at DESC LIMIT 2;
SQL
}

export_rows() {
  local dest="$OUT_DIR/stock_news_live.csv.gz" tmp="$OUT_DIR/.stock_news_live.csv.gz.tmp"
  echo "COPY (SELECT ticker, title, url, published_at, source, entity_id, instrument_id, observed_at, created_at FROM stock_news ORDER BY created_at) TO STDOUT WITH CSV HEADER;" \
    | remote_psql | gzip > "$tmp"
  mv "$tmp" "$dest"
  echo "Gravado: $dest ($(($(gzip -dc "$dest" | wc -l) - 1)) linhas, contando quebras dentro de títulos)"
}

mkdir -p "$OUT_DIR"
case "${1:-}" in
  stats)  assert_read_only; stats ;;
  export) assert_read_only; export_rows ;;
  *) echo "Uso: bash news_signal/export_prod.sh {stats|export}" >&2; exit 2 ;;
esac
