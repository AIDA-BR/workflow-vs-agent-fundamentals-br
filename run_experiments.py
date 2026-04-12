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
"""

import asyncio
from dotenv import load_dotenv

from src.experiments import ExperimentMetadata, Intensity, Model
from src.experiments.manager.config import STOCKS
from main_workflow import run_experiment

load_dotenv()


# Define the 4 experiment variations
EXPERIMENTS = [
    {
        "name": "Variação 1: Sem módulo de fato relevante (GPT-5-mini)",
        "config": ExperimentMetadata(
            model=Model.GPT_5_MINI,
            write_folder="results_v2/sem_fato_relevante_gpt5mini",
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
            write_folder="results_v2/completo_gpt5mini",
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
            write_folder="results_v2/completo_sabiazinho4",
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
            write_folder="results_v2/hibrido_fatos_sabiazinho4_gestor_gpt5mini",
            max_turns=15,
            reasoning=Intensity.MEDIUM,
            verbosity=Intensity.MEDIUM,
            reflection=False,
            use_fundamental_analysis=True,
            use_material_facts=True,
        ),
    },
]


async def main():
    """Run all experiment variations sequentially."""
    print("=" * 80)
    print("INICIANDO EXECUÇÃO DAS 4 VARIAÇÕES DE EXPERIMENTO")
    print("=" * 80)
    print()

    for i, experiment_info in enumerate(EXPERIMENTS, 1):
        print("=" * 80)
        print(f"EXECUTANDO: {experiment_info['name']}")
        print(f"Saída: {experiment_info['config'].write_folder}/")
        print(f"Ações: {len(STOCKS)} (5 iniciais + 4 novas)")
        print("=" * 80)
        print()

        await run_experiment(experiment_info["config"], STOCKS)

        print()
        print(f"✓ Variação {i} concluída com sucesso!")
        print()

    print("=" * 80)
    print("TODAS AS 4 VARIAÇÕES FORAM EXECUTADAS COM SUCESSO!")
    print("Resultados salvos em: results_v2/")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
