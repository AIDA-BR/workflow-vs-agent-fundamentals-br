# Workflow vs Agent — Análise Fundamentalista de Ações Brasileiras

Experimento comparando abordagens de **workflow** e **agente autônomo** para análise fundamentalista de ações do mercado brasileiro, usando a API da OpenAI.

## Estrutura do projeto

```
./
├── main.py                         # Experimento: análise fundamentalista (agent vs workflow)
├── main_workflow.py                # Experimento: casa de investimento (analista + gestor)
├── dev.env                         # Variáveis de ambiente (copiar para .env)
├── pyproject.toml
├── scripts/
│   ├── evaluation_final.ipynb      # Notebook com os resultados reportados
│   ├── extract_fundamental_analysis.py
│   ├── parse_cvm.ipynb
│   └── parse_prices.ipynb
└── src/
    ├── settings.py                 # Centraliza caminhos lidos de variáveis de ambiente
    ├── db/                         # Consultas SQL (CVM DFP/ITR e preços)
    ├── tools/                      # Ferramentas OpenAI Agents (function tools)
    ├── financial_agents/           # Definições de agentes (analista, gestor)
    └── experiments/
        ├── fundamental_analysis/   # Experimento agent vs workflow (main.py)
        │   ├── agent.py
        │   ├── workflow.py
        │   └── config.py           # Lista de ações (STOCKS)
        └── manager/                # Experimento casa de investimento (main_workflow.py)
            ├── fundamental_analyst.py
            ├── manager.py
            └── config.py
```

## Configuração

### 1. Instalar dependências

Requer [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
uv sync
```

### 2. Preparar base de dados

Descompacte as bases de dados na pasta `data/`:

```
data/
├── cvm.db          # Formulários DFP/ITR da CVM
├── prices.db       # Histórico de preços (COTAHIST)
└── gold.csv        # Preços de referência para os experimentos
```

### 3. Configurar variáveis de ambiente

Copie `dev.env` para `.env` e atualize os valores:

```bash
cp dev.env .env
```

Variáveis obrigatórias em `.env`:

| Variável | Descrição |
|---|---|
| `OPENAI_API_KEY` | Chave da API OpenAI |
| `DB_PATH` | Caminho para `cvm.db` |
| `PRICE_DB_PATH` | Caminho para `prices.db` |
| `PRICE_FILE` | Caminho para o CSV de preços de referência |
| `WRITE_FOLDER` | Pasta de saída dos resultados (padrão: `results`) |

## Execução

### Experimento: análise fundamentalista (agent vs workflow)

Compara as abordagens agent e workflow na tarefa de computar indicadores fundamentalistas para uma lista de ações.

```bash
uv run main.py
```

Resultados salvos em `results/<model>/agent_<reflection>/` e `results/<model>/workflow_<reflection>/`.

### Experimento: casa de investimento

Simula uma casa de investimento com dois agentes em sequência: um analista fundamentalista e um gestor de carteira, iterando mensalmente sobre 2024–2025.

```bash
uv run main_workflow.py
```

Resultados salvos em `results/<stock_id>/`.

### Avaliação

Abra o notebook com os resultados reportados no paper:

```bash
uv run jupyter lab scripts/evaluation_final.ipynb
```
