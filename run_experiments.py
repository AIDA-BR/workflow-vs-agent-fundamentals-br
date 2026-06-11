"""
Run multiple experiment variations of the investment house workflow.

This script executes 4 different experiment configurations, each with different
models and enabled/disabled modules. Results are saved to results_v2/ with
intuitive folder names for each variation.

Variations:
1. Without material facts, GPT-5-mini → sem_fato_relevante_gpt5mini/
2. Full system with GPT-5-mini → completo_gpt5mini/
3. Full system with Sabiazinho-4 → completo_sabiazinho4/
4. Hybrid: material facts with Sabiazinho-4, manager with GPT-5-mini → hibrido_fatos_sabiazinho4_gestor_gpt5mini/
5. Technical analyst via spreadsheet, GPT-5-mini → results_v3/tecnico_planilha_gpt5mini/
6. Technical analyst via charts/images, GPT-5-mini → results_v3/tecnico_imagem_gpt5mini/
7. Technical analyst via spreadsheet+images, GPT-5-mini → results_v3/tecnico_hibrido_gpt5mini/

Variations 1-4 are already computed in results_v2/; only 5-7 (new, results_v3/) are produced here.
"""

import asyncio
from dotenv import load_dotenv

from src.experiments import ExperimentMetadata, Intensity, Model, TechnicalVariant
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

# Define the 4 experiment variations
EXPERIMENTS = [
    # {
    #     "name": "Variação 1: Sem módulo de fato relevante (GPT-5-mini)",
    #     "config": ExperimentMetadata(
    #         model=Model.GPT_5_MINI,
    #         write_folder="results_v2/sem_fato_relevante_gpt5mini",
    #         max_turns=15,
    #         reasoning=Intensity.MEDIUM,
    #         verbosity=Intensity.MEDIUM,
    #         reflection=False,
    #         use_fundamental_analysis=True,
    #         use_material_facts=False,
    #     ),
    # },
    # {
    #     "name": "Variação 2: Sistema completo (GPT-5-mini)",
    #     "config": ExperimentMetadata(
    #         model=Model.GPT_5_MINI,
    #         write_folder="results_v2/completo_gpt5mini",
    #         max_turns=15,
    #         reasoning=Intensity.MEDIUM,
    #         verbosity=Intensity.MEDIUM,
    #         reflection=False,
    #         use_fundamental_analysis=True,
    #         use_material_facts=True,
    #     ),
    # },
    # {
    #     "name": "Variação 3: Sistema completo (Sabiazinho-4)",
    #     "config": ExperimentMetadata(
    #         model=Model.SABIAZINHO_4,
    #         write_folder="results_v2/completo_sabiazinho4",
    #         max_turns=15,
    #         reasoning=Intensity.MEDIUM,
    #         verbosity=Intensity.MEDIUM,
    #         reflection=False,
    #         use_fundamental_analysis=True,
    #         use_material_facts=True,
    #     ),
    # },
    # {
    #     "name": "Variação 4: Híbrido - fatos com Sabiazinho-4, gestor com GPT-5-mini",
    #     "config": ExperimentMetadata(
    #         model=Model.GPT_5_MINI,
    #         material_facts_model=Model.SABIAZINHO_4,
    #         write_folder="results_v2/hibrido_fatos_sabiazinho4_gestor_gpt5mini",
    #         max_turns=15,
    #         reasoning=Intensity.MEDIUM,
    #         verbosity=Intensity.MEDIUM,
    #         reflection=False,
    #         use_fundamental_analysis=True,
    #         use_material_facts=True,
    #     ),
    # },
    # --- Variações do analista técnico (GPT-5-mini, sistema completo + técnico) ---
    # Mesmos indicadores nas três; muda apenas a modalidade de apresentação.
    # Salvas em results_v3/; baseline sem técnico: results_v2/completo_gpt5mini (Variação 2).
    {
        "name": "Variação 5: Técnico via planilha (GPT-5-mini)",
        "config": ExperimentMetadata(
            model=Model.GPT_5_MINI,
            write_folder="results_v3/tecnico_planilha_gpt5mini",
            max_turns=15,
            reasoning=Intensity.MEDIUM,
            verbosity=Intensity.MEDIUM,
            reflection=False,
            use_fundamental_analysis=True,
            use_material_facts=True,
            use_technical_analysis=True,
            technical_variant=TechnicalVariant.PLANILHA,
        ),
    },
    {
        "name": "Variação 6: Técnico via imagem (GPT-5-mini)",
        "config": ExperimentMetadata(
            model=Model.GPT_5_MINI,
            write_folder="results_v3/tecnico_imagem_gpt5mini",
            max_turns=15,
            reasoning=Intensity.MEDIUM,
            verbosity=Intensity.MEDIUM,
            reflection=False,
            use_fundamental_analysis=True,
            use_material_facts=True,
            use_technical_analysis=True,
            technical_variant=TechnicalVariant.IMAGEM,
        ),
    },
    {
        "name": "Variação 7: Técnico híbrido planilha+imagem (GPT-5-mini)",
        "config": ExperimentMetadata(
            model=Model.GPT_5_MINI,
            write_folder="results_v3/tecnico_hibrido_gpt5mini",
            max_turns=15,
            reasoning=Intensity.MEDIUM,
            verbosity=Intensity.MEDIUM,
            reflection=False,
            use_fundamental_analysis=True,
            use_material_facts=True,
            use_technical_analysis=True,
            technical_variant=TechnicalVariant.HIBRIDO,
        ),
    },
]


async def main():
    """Pre-fetch raw material facts once, then run all experiment variations sequentially."""
    print("=" * 80)
    print(f"INICIANDO EXECUÇÃO DE {len(EXPERIMENTS)} VARIAÇÃO(ÕES) DE EXPERIMENTO")
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

    # Caches de fatos relevantes compartilhados entre as 3 variações técnicas:
    # o analista de fatos relevantes (resumos mensais + consolidação de 6 meses)
    # roda UMA vez (na primeira variação) e é reaproveitado nas demais — custo
    # marginal nulo, pois todas usam o mesmo modelo (GPT-5-mini) e as mesmas datas.
    shared_monthly_cache: dict = {}
    shared_six_month_cache: dict = {}

    # --- Run each experiment using the pre-fetched cache ---
    for i, experiment_info in enumerate(EXPERIMENTS, 1):
        print("=" * 80)
        print(f"EXECUTANDO: {experiment_info['name']}")
        print(f"Saída: {experiment_info['config'].write_folder}/")
        print(f"Ações: {len(STOCKS)} (5 iniciais + 4 novas)")
        print("=" * 80)
        print()

        # Pass raw_facts_cache only to experiments that use material facts
        cache = raw_facts_cache if experiment_info["config"].use_material_facts else None
        await run_experiment(
            experiment_info["config"],
            STOCKS,
            raw_facts_cache=cache,
            monthly_summary_cache=shared_monthly_cache,
            six_month_cache=shared_six_month_cache,
        )

        print()
        print(f"Variação {i} concluída.")
        print()

    print("=" * 80)
    print(f"TODAS AS {len(EXPERIMENTS)} VARIAÇÃO(ÕES) FORAM EXECUTADAS COM SUCESSO!")
    print("Resultados salvos em: results_v3/")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
