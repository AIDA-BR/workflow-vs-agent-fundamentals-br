from main_baseline import run as run_baseline
from main_workflow import run as run_manager

if __name__ == "__main__":
    print("=== Running manager experiment (results/manager/) ===")
    run_manager()
    print("=== Running baseline experiment (results/baseline/) ===")
    run_baseline()
