"""
Run multiple experiment variations of the investment house workflow.

This script executes 4 different experiment configurations, each with different
models and enabled/disabled modules. Results are saved to <output-root>/ (default:
results_v2/) with one folder per variation.

Variations (paper column in parentheses):
1. Without material facts, GPT-5-mini → sem_fato_relevante_gpt5mini/ (Fund.Rule)
2. Full system with GPT-5-mini → completo_gpt5mini/ (+FactsGPT)
3. Full system with Sabiazinho-4 → completo_sabiazinho4/ (+FactsSabiá)
4. Hybrid: material facts with Sabiazinho-4, manager with GPT-5-mini
   → hibrido_fatos_sabiazinho4_gestor_gpt5mini/ (Hybrid)

Runs are resumable: a stock/month whose output already exists in the folder is skipped.
Use a fresh --output-root to re-run from scratch without touching existing results.

Usage:
    uv run run_experiments.py --output-root reproduced
    uv run run_experiments.py --output-root reproduced --only sem_fato_relevante_gpt5mini completo_gpt5mini
"""

import argparse
import asyncio
from dotenv import load_dotenv

from src.experiments import ExperimentMetadata, Intensity, Model
from src.experiments.manager.config import STOCKS
from src.tools.material_facts import prefetch_all_raw_facts, _RAW_FACTS_CACHE_PATH
from main_workflow import run_experiment

load_dotenv()

# (year, month) pairs for all 6-month windows used by analyses 2024-01 → 2025-12
# First window: 2023-07..2023-12; last window: 2025-06..2025-11
_PREFETCH_YEAR_MONTHS = [
    (y, m)
    for y in range(2023, 2026)
    for m in range(1, 13)
    if (y, m) >= (2023, 7) and (y, m) <= (2025, 11)
]

# Define the 4 experiment variations. `write_folder` is relative to --output-root.
EXPERIMENTS = [
    {
        "name": "Variação 1: Sem módulo de fato relevante (GPT-5-mini)",
        "config": ExperimentMetadata(
            model=Model.GPT_5_MINI,
            write_folder="sem_fato_relevante_gpt5mini",
            max_turns=15,
            reasoning=Intensity.MEDIUM,
            verbosity=Intensity.MEDIUM,
            reflection=False,
            use_fundamental_analysis=True,
            use_material_facts=False,
        ),
    },
    {
        "name": "Variação 2: Sistema completo (GPT-5-mini)",
        "config": ExperimentMetadata(
            model=Model.GPT_5_MINI,
            write_folder="completo_gpt5mini",
            max_turns=15,
            reasoning=Intensity.MEDIUM,
            verbosity=Intensity.MEDIUM,
            reflection=False,
            use_fundamental_analysis=True,
            use_material_facts=True,
        ),
    },
    {
        "name": "Variação 3: Sistema completo (Sabiazinho-4)",
        "config": ExperimentMetadata(
            model=Model.SABIAZINHO_4,
            write_folder="completo_sabiazinho4",
            max_turns=15,
            reasoning=Intensity.MEDIUM,
            verbosity=Intensity.MEDIUM,
            reflection=False,
            use_fundamental_analysis=True,
            use_material_facts=True,
        ),
    },
    {
        "name": "Variação 4: Híbrido - fatos com Sabiazinho-4, gestor com GPT-5-mini",
        "config": ExperimentMetadata(
            model=Model.GPT_5_MINI,
            material_facts_model=Model.SABIAZINHO_4,
            write_folder="hibrido_fatos_sabiazinho4_gestor_gpt5mini",
            max_turns=15,
            reasoning=Intensity.MEDIUM,
            verbosity=Intensity.MEDIUM,
            reflection=False,
            use_fundamental_analysis=True,
            use_material_facts=True,
        ),
    },
]


def parse_args() -> argparse.Namespace:
    folders = [e["config"].write_folder for e in EXPERIMENTS]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--output-root",
        default="results_v2",
        help="Root folder where each variation's folder is written (default: results_v2)",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        choices=folders,
        metavar="FOLDER",
        help=f"Run only these variations (choices: {', '.join(folders)})",
    )
    return parser.parse_args()


async def main(output_root: str, only: list[str] | None = None):
    """Pre-fetch raw material facts once, then run all experiment variations sequentially."""
    experiments = [e for e in EXPERIMENTS if only is None or e["config"].write_folder in only]
    for e in experiments:
        e["config"].write_folder = f"{output_root}/{e['config'].write_folder}"

    print("=" * 80)
    print(f"INICIANDO EXECUÇÃO DE {len(experiments)} VARIAÇÕES DE EXPERIMENTO")
    print("=" * 80)
    print()

    # --- Pre-fetch raw material facts (shared across all experiments) ---
    print("PRÉ-FETCH: baixando e convertendo fatos relevantes (2023-07 a 2025-11)...")
    raw_facts_cache = prefetch_all_raw_facts(
        stocks=STOCKS,
        year_months=_PREFETCH_YEAR_MONTHS,
        cache_path=_RAW_FACTS_CACHE_PATH,
    )
    print(f"Pré-fetch concluído: {len(raw_facts_cache)} entradas em cache.")
    print()

    # --- Run each experiment using the pre-fetched cache ---
    for i, experiment_info in enumerate(experiments, 1):
        print("=" * 80)
        print(f"EXECUTANDO: {experiment_info['name']}")
        print(f"Saída: {experiment_info['config'].write_folder}/")
        print(f"Ações: {len(STOCKS)} (5 iniciais + 4 novas)")
        print("=" * 80)
        print()

        # Pass raw_facts_cache only to experiments that use material facts
        cache = raw_facts_cache if experiment_info["config"].use_material_facts else None
        await run_experiment(experiment_info["config"], STOCKS, raw_facts_cache=cache)

        print()
        print(f"Variação {i} concluída.")
        print()

    print("=" * 80)
    print("TODAS AS VARIAÇÕES FORAM EXECUTADAS COM SUCESSO!")
    print(f"Resultados salvos em: {output_root}/")
    print("=" * 80)


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.output_root, args.only))
