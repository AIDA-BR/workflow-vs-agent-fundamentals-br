"""
Experimento faltante: Analista Fundamentalista (LLM) + Fatos Relevantes + Gestor,
tudo com GPT-5-mini.

Motivação
---------
Um revisor pediu a comparação do **analista fundamentalista via LLM** combinado com o
**agente de fatos relevantes**. Todos os experimentos de `results_v2/` usam o analista
fundamentalista determinístico (SQL), nunca o analista via LLM. Esta modalidade junta:

- Analista fundamentalista **via LLM** — saídas já existentes em `results/manager/`
  (modalidade "(Ferreira et al., 2026)", fundamental analysis only, sem fatos).
- Fatos relevantes **GPT-5-mini** — relatórios já existentes em
  `results_v2/completo_gpt5mini/{ACAO}/{data}_material_facts_0.txt`.
- Gestor **GPT-5-mini** — único componente efetivamente reexecutado aqui.

Para otimizar, NÃO reexecutamos o analista nem o sumarizador de fatos: ambos são lidos
do disco. Apenas o gestor roda. Resultado salvo em
`results_v2/completo_analista_llm_gpt5mini/`.

A lógica espelha `main_workflow.run_experiment`, reutilizando seus helpers.
"""

import asyncio
import json
import os
import shutil
import time
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

from src.experiments import Model
from src.experiments.manager import manager as financial_manager
from src.experiments.manager.config import STOCKS
from main_workflow import (
    _get_last_manager_decision,
    _parse_financial_manager_output,
    _save_results,
)

load_dotenv()

# --- Configuração da modalidade --------------------------------------------------
MODEL = Model.GPT_5_MINI
MAX_TURNS = 15

# Fonte dos indicadores do analista fundamentalista VIA LLM (já executado)
ANALYST_LLM_FOLDER = "results/manager"
# Fonte dos relatórios de fatos relevantes em GPT-5-mini (já executado)
MATERIAL_FACTS_FOLDER = "results_v2/completo_gpt5mini"
# Pasta de saída desta nova modalidade
WRITE_FOLDER = "results_v2/completo_analista_llm_gpt5mini"

# Campos de "decisão anterior" que devem ser recalculados a cada passo a partir das
# decisões do NOVO gestor (e não copiados da execução de origem).
_PREV_DECISION_KEYS = (
    "JUSTIFICATIVA_PREVIA",
    "PRECO_ALVO_ANTERIOR",
    "RECOMENDACAO_ANTERIOR",
)

# Mapeia stock_id -> StockInput (o gestor precisa de name/cnpj)
_STOCK_BY_ID = {s.stock_id: s for s in STOCKS}


def _load_json(path: str):
    with open(path) as f:
        return json.load(f)


def _read_material_facts_report(stock_id: str, analysis_date: str) -> str:
    """Lê o relatório de fatos relevantes (GPT-5-mini) já gerado em disco."""
    path = f"{MATERIAL_FACTS_FOLDER}/{stock_id}/{analysis_date}_material_facts_0.txt"
    if not os.path.exists(path):
        print(f"  AVISO: relatório de fatos não encontrado: {path} (usando string vazia)")
        return ""
    with open(path) as f:
        return f.read()


def _copy_archive_files(stock_id: str, analysis_date: str) -> None:
    """Copia o analyst_0.json (LLM) e o material_facts_0.txt para a pasta de saída,
    apenas para arquivamento/rastreabilidade da modalidade."""
    dst_dir = f"{WRITE_FOLDER}/{stock_id}"
    os.makedirs(dst_dir, exist_ok=True)

    analyst_src = f"{ANALYST_LLM_FOLDER}/{stock_id}/{analysis_date}_analyst_0.json"
    if os.path.exists(analyst_src):
        shutil.copy2(analyst_src, f"{dst_dir}/{analysis_date}_analyst_0.json")

    facts_src = f"{MATERIAL_FACTS_FOLDER}/{stock_id}/{analysis_date}_material_facts_0.txt"
    if os.path.exists(facts_src):
        shutil.copy2(facts_src, f"{dst_dir}/{analysis_date}_material_facts_0.txt")


async def run() -> None:
    os.makedirs(WRITE_FOLDER, exist_ok=True)

    # Registros consolidados do analista LLM (indicadores + preço) por ação×mês
    source_records = _load_json(f"{ANALYST_LLM_FOLDER}/results_sample.json")

    # Estado acumulado (resumível)
    fundamental_analyses: list = []
    manager_decisions: list = []
    if os.path.exists(f"{WRITE_FOLDER}/results_sample.json"):
        fundamental_analyses = _load_json(f"{WRITE_FOLDER}/results_sample.json")
        manager_decisions = _load_json(f"{WRITE_FOLDER}/decisions_sample.json")

    while True:
        is_error = False
        try:
            for stock in STOCKS:
                stock_id = stock.stock_id

                # Registros desta ação, em ordem cronológica
                stock_records = sorted(
                    (r for r in source_records if r["ACAO"] == stock_id),
                    key=lambda r: r["DATA_DO_PREGAO"],
                )

                for record in stock_records:
                    analysis_date = record["DATA_DO_PREGAO"]
                    analysis_dt = datetime.fromisoformat(analysis_date)

                    manager_path = f"{WRITE_FOLDER}/{stock_id}/{analysis_date}_manager_0.json"
                    if os.path.exists(manager_path):
                        continue

                    print(f"Gestor: {stock_id} em {analysis_date}")
                    start_time = time.time()

                    daily_stock_price = float(record["PRECO_ULTIMO_NEGOCIO"])

                    # --- Reconstrói o registro de indicadores fielmente ao pipeline ---
                    # Indicadores do analista LLM + preço (todas as chaves de origem,
                    # exceto a "decisão anterior", que vem do NOVO gestor em sequência).
                    base = {k: v for k, v in record.items() if k not in _PREV_DECISION_KEYS}
                    last_manager_decision = _get_last_manager_decision(manager_decisions, stock_id)
                    fundamental_analyses.append({**base, **last_manager_decision})

                    indicators = pd.DataFrame(fundamental_analyses)
                    indicators = (
                        indicators[indicators["ACAO"] == stock_id]
                        .sort_values("DATA_DO_PREGAO", ascending=True)
                        .tail(12)
                    )
                    indicators_str = indicators.to_string()

                    # --- Fatos relevantes (GPT-5-mini) lidos do disco ---
                    material_facts_report_str = _read_material_facts_report(stock_id, analysis_date)

                    # --- Roda apenas o gestor ---
                    decision = await financial_manager.run(
                        stock=stock,
                        stock_price=daily_stock_price,
                        date=analysis_dt,
                        max_turns=MAX_TURNS,
                        indicators=indicators_str,
                        material_facts_report=material_facts_report_str,
                        model=MODEL,
                    )

                    end_time = time.time()

                    _save_results(
                        write_folder=WRITE_FOLDER,
                        stock_id=stock_id,
                        analysis_date=analysis_date,
                        agent_role="manager",
                        result=decision,
                        elapsed_time=end_time - start_time,
                        experiment_id=0,
                    )
                    _copy_archive_files(stock_id, analysis_date)

                    parsed = _parse_financial_manager_output(
                        decision,
                        analysis_dt,
                        end_time - start_time,
                        stock_id,
                    )
                    manager_decisions.append(parsed)

                    # Checkpoints
                    with open(f"{WRITE_FOLDER}/results_sample.json", "w") as f:
                        json.dump(fundamental_analyses, f, indent=4)
                    with open(f"{WRITE_FOLDER}/decisions_sample.json", "w") as f:
                        json.dump(manager_decisions, f, indent=4)
        except Exception as exc:
            print(f"Erro ({exc!r}), tentando novamente em 1 minuto...")
            time.sleep(60)
            is_error = True

        if not is_error:
            break

    print("=" * 80)
    print("CONCLUÍDO. Resultados em:", WRITE_FOLDER)
    print(f"Decisões: {len(manager_decisions)} | Registros: {len(fundamental_analyses)}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run())
