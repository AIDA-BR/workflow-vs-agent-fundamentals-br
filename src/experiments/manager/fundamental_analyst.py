from datetime import datetime

from src.experiments import StockInput
from src.experiments.fundamental_analysis.workflow import get_db_fields, get_total_shares
from src.financial_agents.financial_analyst import IndicatorOutput, compute_indicators


# ---------------------------------------------------------------------------
# Lightweight result wrapper — satisfies get_result() in src/experiments/utils.py
# without invoking any LLM.
# ---------------------------------------------------------------------------


class _Usage:
    requests = 0
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0


class _ContextWrapper:
    usage = _Usage()


class WorkflowResult:
    """Mimics the RunResult interface expected by get_result() and _save_results()."""

    def __init__(self, output: IndicatorOutput) -> None:
        self.context_wrapper = _ContextWrapper()
        self.new_items: list = []
        self.final_output = output


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run(
    stock: StockInput,
    stock_price: float,
    date: str | datetime,
) -> WorkflowResult:
    """Compute fundamental indicators directly from the CVM database.

    Replaces the LLM-based analysis with deterministic SQL queries, exactly as
    done in src/experiments/fundamental_analysis/workflow.py.

    The returned WorkflowResult exposes the same interface as RunResult so that
    main_workflow.py can call get_result() and _save_results() without changes.
    """
    if isinstance(date, str):
        date = datetime.fromisoformat(date)

    date_str = date.strftime("%Y-%m-%d")

    db_fields = get_db_fields(cnpj=stock.cnpj, date=date_str)
    total_shares = get_total_shares(
        cnpj=stock.cnpj, date=date_str, shares_multiplier=stock.shares_multiplier
    )
    output = compute_indicators(db_fields=db_fields, price=stock_price, total_shares=total_shares)

    return WorkflowResult(output=output)
