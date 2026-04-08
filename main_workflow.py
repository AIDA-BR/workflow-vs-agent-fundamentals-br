import asyncio
import json
import os
import time

import finbr.dias_uteis as dus
import pandas as pd
from agents import RunResult
from datetime import datetime, timedelta
from dotenv import load_dotenv

from src.db import get_stock_daily_info
from src.db.base_query import ResponseFormat
from src.experiments import ExperimentMetadata, Intensity, Model
from src.experiments.manager import fundamental_analyst, manager as financial_manager
from src.experiments.manager.config import STOCKS
from src.experiments.manager.material_facts_report import (
    format_six_month_report,
    get_six_month_summary,
)
from src.experiments.utils import get_result
from src.financial_agents.material_facts_summarizer import MonthlySummary
from src.settings import WRITE_FOLDER

load_dotenv()


def _year_months(start: tuple[int, int], end: tuple[int, int]):
    """Yield (year, month) pairs from start to end, inclusive."""
    y, m = start
    while (y, m) <= end:
        yield y, m
        m += 1
        if m > 12:
            m, y = 1, y + 1


def _get_first_workday(year, month):
    date = datetime(year, month, 1)
    while date.weekday() > 4 or not dus.dia_util(date):
        date += timedelta(days=1)
    return date


def get_last_stock_report_date(date: datetime) -> datetime:
    if date.month <= 3:
        year = date.year - 1
        return datetime(year, 9, 30)
    elif 3 < date.month <= 6:
        year = date.year - 1
        return datetime(year, 12, 31)
    elif 6 < date.month <= 9:
        return datetime(date.year, 3, 31)
    else:
        return datetime(date.year, 6, 30)


def _parse_fundamental_analyst_output(result: RunResult, elapsed_time: float) -> dict:
    """
    Return a dictionary containing the fundamental analysis indicators and their values.

    Parameters
    ----------
    result : RunResult
        The result of the financial analysis.
    elapsed_time : float
        The elapsed time of the analysis.

    Returns
    -------
    dict
        A dictionary containing the fundamental analysis indicators and their values.
    """
    fundamental_analysis = get_result(result, elapsed_time)

    fundamental_indicators = {
        str(f["indicator"]): f["value"]
        for f in fundamental_analysis.get("output", {}).get("indicators", [])
    }
    return fundamental_indicators


def _parse_financial_manager_output(
    result: RunResult, analysis_date: str, elapsed_time: float, stock_id: str
) -> dict:
    manager_result = get_result(result, elapsed_time).get("output", {})
    manager_result["analysis_date"] = analysis_date.strftime("%Y-%m-%d")
    manager_result["stock_id"] = stock_id
    return manager_result


def _get_daily_price_info(stock_id: str, daily_stock_info: dict, report_date: str) -> dict:
    """
    Return a dictionary containing the daily price information of a stock.

    Parameters
    ----------
    stock_id : str
        The ID of the stock.
    daily_stock_info : dict
        A dictionary containing the daily price information of the stock.

    Returns
    -------
    dict
        A dictionary containing the daily price information of the stock.
    """
    price_info = {}
    price_info["ACAO"] = stock_id
    price_info["DATA_DO_PREGAO"] = daily_stock_info["DATA_DO_PREGAO"]
    price_info["PRECO_DE_ABERTURA"] = daily_stock_info["PRECO_DE_ABERTURA"]
    price_info["PRECO_MINIMO"] = daily_stock_info["PRECO_MINIMO"]
    price_info["PRECO_MAXIMO"] = daily_stock_info["PRECO_MAXIMO"]
    price_info["PRECO_ULTIMO_NEGOCIO"] = daily_stock_info["PRECO_ULTIMO_NEGOCIO"]
    price_info["PRECO_MEDIO"] = daily_stock_info["PRECO_MEDIO"]
    price_info["PRECO_MELHOR_OFERTA_DE_COMPRA"] = daily_stock_info["PRECO_MELHOR_OFERTA_DE_COMPRA"]
    price_info["QUANTIDADE_NEGOCIADA"] = daily_stock_info["QUANTIDADE_NEGOCIADA"]
    price_info["VOLUME_TOTAL_NEGOCIADO"] = daily_stock_info["VOLUME_TOTAL_NEGOCIADO"]
    price_info["DATA_BALANCO_PROCESSADO"] = report_date.strftime("%Y-%m-%d")
    return price_info


def _get_last_manager_decision(decisions: list, stock_id: str) -> dict:
    decisions_ = [d for d in decisions if d["stock_id"] == stock_id]
    if len(decisions_) == 0:
        return {
            "JUSTIFICATIVA_PREVIA": "N/A",
            "PRECO_ALVO_ANTERIOR": "N/A",
            "RECOMENDACAO_ANTERIOR": "N/A",
        }
    return {
        "JUSTIFICATIVA_PREVIA": decisions_[-1]["justification"],
        "PRECO_ALVO_ANTERIOR": decisions_[-1]["target_price"],
        "RECOMENDACAO_ANTERIOR": decisions_[-1]["recommendation"],
    }


def _save_results(
    write_folder: str,
    stock_id: str,
    analysis_date: str,
    agent_role: str,
    result: RunResult,
    elapsed_time: float,
    experiment_id: int,
) -> None:
    write_folder = f"{write_folder}/{stock_id}"
    os.makedirs(write_folder, exist_ok=True)
    agent_result = get_result(result, elapsed_time)

    with open(f"{write_folder}/{analysis_date}_{agent_role}_{experiment_id}.json", "w") as f:
        json.dump(agent_result, f, indent=4)


async def main():
    manager_decisions = []
    fundamental_analyses = []
    monthly_summary_cache: dict = {}

    experiment = ExperimentMetadata(
        model=Model.SABIAZINHO_4,
        write_folder=WRITE_FOLDER,
        max_turns=15,
        reasoning=Intensity.MEDIUM,
        verbosity=Intensity.MEDIUM,
        reflection=False,
    )

    if os.path.exists(f"{experiment.write_folder}/results_sample.json"):
        with open(f"{experiment.write_folder}/results_sample.json") as f:
            fundamental_analyses = json.load(f)

        with open(f"{experiment.write_folder}/decisions_sample.json") as f:
            manager_decisions = json.load(f)

    cache_path = f"{experiment.write_folder}/monthly_summary_cache.json"
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            raw_cache = json.load(f)
        for k, v in raw_cache.items():
            parts = k.split("|")
            monthly_summary_cache[(parts[0], int(parts[1]), int(parts[2]))] = MonthlySummary(**v)

    while True:
        is_error = False
        try:
            for stock in STOCKS:
                for year, month in _year_months(start=(2024, 1), end=(2025, 12)):
                    analysis_date = _get_first_workday(year, month)
                    print(f"Analisando {stock.stock_id} em {analysis_date}")

                    if os.path.exists(
                        f"{experiment.write_folder}/{stock.stock_id}/{analysis_date.strftime('%Y-%m-%d')}_analyst_0.json"
                    ):
                        continue

                    start_time = time.time()

                    # Get stock price in the day
                    daily_stock_info = get_stock_daily_info(
                        stock_id=stock.stock_id,
                        date=analysis_date,
                        response_format=ResponseFormat.DICT,
                    )
                    if len(daily_stock_info) == 0:
                        continue
                    daily_stock_price = float(daily_stock_info[0]["PRECO_ULTIMO_NEGOCIO"])

                    # Get last quarter reports date (previous 3 months)
                    report_date = get_last_stock_report_date(analysis_date)

                    # --- Fundamental analysis module ---
                    if experiment.use_fundamental_analysis:
                        result = fundamental_analyst.run(
                            stock=stock,
                            stock_price=daily_stock_price,
                            date=report_date,
                        )

                        end_time = time.time()

                        _save_results(
                            write_folder=experiment.write_folder,
                            stock_id=stock.stock_id,
                            analysis_date=analysis_date.strftime("%Y-%m-%d"),
                            agent_role="analyst",
                            result=result,
                            elapsed_time=end_time - start_time,
                            experiment_id=0,
                        )

                        fundamental_indicators = _parse_fundamental_analyst_output(
                            result, end_time - start_time
                        )
                    else:
                        end_time = time.time()
                        fundamental_indicators = {}

                    # Get price info
                    price_info = _get_daily_price_info(
                        stock_id=stock.stock_id,
                        daily_stock_info=daily_stock_info[0],
                        report_date=report_date,
                    )
                    # Last manager decision
                    last_manager_decision = _get_last_manager_decision(
                        manager_decisions, stock.stock_id
                    )

                    fundamental_analyses.append(
                        {
                            **fundamental_indicators,
                            **price_info,
                            **last_manager_decision,
                        }
                    )

                    indicators_str = ""
                    if experiment.use_fundamental_analysis:
                        indicators = pd.DataFrame(fundamental_analyses)
                        indicators = (
                            indicators[indicators["ACAO"] == stock.stock_id]
                            .sort_values("DATA_DO_PREGAO", ascending=True)
                            .tail(12)
                        )
                        indicators_str = indicators.to_string()

                    # --- Material facts module ---
                    material_facts_report_str = ""
                    if experiment.use_material_facts:
                        six_month_summary = await get_six_month_summary(
                            stock=stock,
                            analysis_date=analysis_date,
                            model=experiment.model,
                            cache=monthly_summary_cache,
                        )
                        material_facts_report_str = format_six_month_report(six_month_summary)

                        stock_folder = f"{experiment.write_folder}/{stock.stock_id}"
                        os.makedirs(stock_folder, exist_ok=True)
                        report_file = (
                            f"{stock_folder}/{analysis_date.strftime('%Y-%m-%d')}"
                            "_material_facts_0.txt"
                        )
                        with open(report_file, "w") as f:
                            f.write(material_facts_report_str)

                    decision = await financial_manager.run(
                        stock=stock,
                        stock_price=daily_stock_price,
                        date=analysis_date,
                        max_turns=experiment.max_turns,
                        indicators=indicators_str,
                        material_facts_report=material_facts_report_str,
                        model=experiment.model,
                    )

                    end_time = time.time()

                    _save_results(
                        write_folder=experiment.write_folder,
                        stock_id=stock.stock_id,
                        analysis_date=analysis_date.strftime("%Y-%m-%d"),
                        agent_role="manager",
                        result=decision,
                        elapsed_time=end_time - start_time,
                        experiment_id=0,
                    )

                    decision = _parse_financial_manager_output(
                        decision,
                        analysis_date,
                        end_time - start_time,
                        stock.stock_id,
                    )
                    manager_decisions.append(decision)

                    with open(f"{experiment.write_folder}/results_sample.json", "w") as f:
                        json.dump(fundamental_analyses, f, indent=4)

                    with open(f"{experiment.write_folder}/decisions_sample.json", "w") as f:
                        json.dump(manager_decisions, f, indent=4)

                    serializable_cache = {
                        f"{k[0]}|{k[1]}|{k[2]}": v.model_dump()
                        for k, v in monthly_summary_cache.items()
                    }
                    with open(cache_path, "w") as f:
                        json.dump(serializable_cache, f, indent=4)
        except Exception:
            print("Error, retrying in 1 minute...")
            time.sleep(60)
            is_error = True

        if not is_error:
            break


if __name__ == "__main__":
    asyncio.run(main())
