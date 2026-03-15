from agents import function_tool
from typing_extensions import TypedDict


class CodeInterpreterInput(TypedDict):
    code: str


@function_tool
def code_interpreter(inp: CodeInterpreterInput) -> dict:
    """
    A function to execute python code, and return the stdout and stderr.

    You should import any libraries that you wish to use. You have access to any libraries the user has installed.

    The code passed to this function is executed in isolation. It should be complete at the time it is passed to this function.

    The result MUST be printed at the end.

    You should interpret the output and errors returned from this function, and attempt to fix any problems.
    If you cannot fix the error, show the code to the user and ask for help

    It is not possible to return graphics or other complicated data from this function. If the user cannot see the output, save it to a file and tell the user.
    """
    import subprocess
    import sys

    try:
        result = subprocess.run([sys.executable, "-c", inp.get("code")], capture_output=True)
        report = f"StdOut:\n{result.stdout}\nStdErr:\n{result.stderr}"
        return {"status": "success", "report": report}
    except Exception as e:
        return {"status": "error", "report": f"Failed to run code: {e}"}
