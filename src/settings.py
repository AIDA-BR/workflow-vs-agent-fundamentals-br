import os

from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.environ["DB_PATH"]
PRICE_DB_PATH = os.environ["PRICE_DB_PATH"]
PRICE_FILE = os.environ["PRICE_FILE"]
WRITE_FOLDER = os.environ.get("WRITE_FOLDER", "results_material_facts")
