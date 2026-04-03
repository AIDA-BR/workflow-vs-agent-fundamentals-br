import time

from dotenv import load_dotenv

from src.experiments import ExperimentMetadata, Intensity, Model
from src.experiments.fundamental_analysis.agent import run as run_agent
from src.experiments.fundamental_analysis.workflow import run as run_workflow
from src.settings import WRITE_FOLDER

load_dotenv()

while True:
    is_error = False
    try:
        print("GPT-4.1 Mini (no reflection)")
        experiment = ExperimentMetadata(
            model=Model.GPT_4_1_MINI,
            write_folder=WRITE_FOLDER,
            max_turns=15,
            reflection=False,
        )
        print("Agent...")
        run_agent(experiment_metadata=experiment)
        print("Workflow...")
        run_workflow(experiment_metadata=experiment)

        print("\n\nGPT-4.1 Mini (with  reflection)")
        experiment = ExperimentMetadata(
            model=Model.GPT_4_1_MINI,
            write_folder=WRITE_FOLDER,
            max_turns=15,
            reflection=True,
        )
        print("Agent...")
        run_agent(experiment_metadata=experiment)
        print("Workflow...")
        run_workflow(experiment_metadata=experiment)

        print("GPT-4.1 Nano (no reflection)")
        experiment = ExperimentMetadata(
            model=Model.GPT_4_1_NANO,
            write_folder=WRITE_FOLDER,
            max_turns=15,
            reflection=False,
        )
        print("Agent...")
        run_agent(experiment_metadata=experiment)
        print("Workflow...")
        run_workflow(experiment_metadata=experiment)

        print("\n\nGPT-4.1 Nano (with  reflection)")
        experiment = ExperimentMetadata(
            model=Model.GPT_4_1_NANO,
            write_folder=WRITE_FOLDER,
            max_turns=15,
            reflection=True,
        )
        print("Agent...")
        run_agent(experiment_metadata=experiment)
        print("Workflow...")
        run_workflow(experiment_metadata=experiment)

        print("GPT-5 Mini (no reflection)")
        experiment = ExperimentMetadata(
            model=Model.GPT_5_MINI,
            write_folder=WRITE_FOLDER,
            max_turns=15,
            reasoning=Intensity.MEDIUM,
            verbosity=Intensity.MEDIUM,
            reflection=False,
        )
        print("Agent...")
        run_agent(experiment_metadata=experiment)
        print("Workflow...")
        run_workflow(experiment_metadata=experiment)

        print("\n\nGPT-5 Mini (with  reflection)")
        experiment = ExperimentMetadata(
            model=Model.GPT_5_MINI,
            write_folder=WRITE_FOLDER,
            max_turns=15,
            reasoning=Intensity.MEDIUM,
            verbosity=Intensity.MEDIUM,
            reflection=True,
        )
        print("Agent...")
        run_agent(experiment_metadata=experiment)
        print("Workflow...")
        run_workflow(experiment_metadata=experiment)

        print("GPT-5 Nano (no reflection)")
        experiment = ExperimentMetadata(
            model=Model.GPT_5_NANO,
            write_folder=WRITE_FOLDER,
            max_turns=15,
            reasoning=Intensity.MEDIUM,
            verbosity=Intensity.MEDIUM,
            reflection=False,
        )
        print("Agent...")
        run_agent(experiment_metadata=experiment)
        print("Workflow...")
        run_workflow(experiment_metadata=experiment)

        print("\n\nGPT-5 Nano (with  reflection)")
        experiment = ExperimentMetadata(
            model=Model.GPT_5_NANO,
            write_folder=WRITE_FOLDER,
            max_turns=15,
            reasoning=Intensity.MEDIUM,
            verbosity=Intensity.MEDIUM,
            reflection=True,
        )
        print("Agent...")
        run_agent(experiment_metadata=experiment)
        print("Workflow...")
        run_workflow(experiment_metadata=experiment)
    except Exception:
        print("Error, retrying in 1 minute...")
        time.sleep(60)
        is_error = True

    if not is_error:
        break
