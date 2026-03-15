import os
import requests


def get_access_token() -> str:
    jwt_url = os.getenv("JWT_MCP_URL")
    data = {
        "username": os.getenv("MCP_USERNAME"),
        "password": os.getenv("MCP_PASSWORD"),
    }
    r = requests.post(jwt_url, params=data)
    token_info = r.json()
    token = token_info["access_token"]
    return token
