# Fundamental Analyst in OpenAI

## Dependencies

You need to have the uv Python package installed. See more details [here](https://docs.astral.sh/uv/getting-started/installation/).

Once installed, run the following command to install the dependencies:

```bash
uv sync
```

Then copy the `dev.env` file in an `.env` one. There, update the `OPENAI_API_KEY` variable with your OpenAI key.

# Execution

There are two fundamental analyst approaches: the workflow and the agentic one. Their execution is available in scripts `main_workflow.py` and `main.py`. You may run then by the following command:

```bash
uv run main.py
```

But before it, update the `price_file` with the path for the file with prices, available in the `fundamental_analysis` folder. Metadata from the experiments can be updated in the `EXPERIMENT_METADATA` constant.
