from dotenv import load_dotenv

from src.experiments import ExperimentMetadata, Model
from src.experiments.fundamental_analysis.workflow import run as run_workflow

load_dotenv()

WRITE_FOLDER = "results/fundamental_analysis_new"

print("Workflow (database-driven)...")
run_workflow(
    experiment_metadata=ExperimentMetadata(
        model=Model.GPT_4_1_MINI,
        write_folder=WRITE_FOLDER,
        max_turns=15,
        reflection=False,
    ),
    n_times=1,
)
