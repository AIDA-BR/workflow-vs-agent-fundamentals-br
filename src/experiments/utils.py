import json

from agents import RunResult
from typing import TypedDict


class LLMUsage(TypedDict):
    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


class AgentResult(TypedDict):
    usage: LLMUsage
    steps: list
    time: float
    output: dict


def get_result(result: RunResult, elapsed_time: float) -> AgentResult:
    usage = result.context_wrapper.usage
    nrequests = usage.requests
    input_tokens = usage.input_tokens
    output_tokens = usage.output_tokens
    total_tokens = usage.total_tokens
    steps = [item.to_input_item() for item in result.new_items]
    return AgentResult(
        usage=LLMUsage(
            requests=nrequests,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        ),
        steps=steps,
        time=elapsed_time,
        output=result.final_output.model_dump(),
    )


def save_results(
    write_folder: str,
    stock_id: str,
    result: RunResult,
    elapsed_time: float,
    experiment_id: int,
) -> None:
    agent_result = get_result(result, elapsed_time)

    with open(f"{write_folder}/{stock_id}_{experiment_id}.json", "w") as f:
        json.dump(agent_result, f, indent=4)

    with open(f"{write_folder}/{stock_id}_output_{experiment_id}.json", "w") as f:
        json.dump(agent_result.get("output"), f, indent=4)
