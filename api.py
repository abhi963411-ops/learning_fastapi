import os
from pathlib import Path

from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import uvicorn as uv
import yaml

app = FastAPI()uvicorn api:app --host 0.0.0.0 --port $PORT
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CONFIG_DIR = Path(__file__).parent
DEFAULT_CONFIG = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}
INTEGER_KEYS = {"port", "workers"}
TRUE_VALUES = {"true", "1", "yes", "on"}


def normalized_key(key: str) -> str:
    key = key.strip().lower()
    if key.startswith("app_"):
        key = key[4:]
    if key == "num_workers":
        return "workers"
    return key


def load_yaml_config(environment: str) -> dict[str, object]:
    config_path = CONFIG_DIR / f"config.{environment}.yaml"
    if not config_path.exists():
        return {}
    with config_path.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file) or {}
    if not isinstance(config, dict):
        raise ValueError(f"{config_path.name} must contain a YAML mapping")
    return {normalized_key(str(key)): value for key, value in config.items()}


def coerce_value(key: str, value: object) -> object:
    if key in INTEGER_KEYS:
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=422,
                detail=f"{key} must be an integer",
            ) from error
    if key == "debug":
        return str(value).strip().lower() in TRUE_VALUES
    return str(value)


def effective_config(overrides: list[str] | None) -> dict[str, object]:
    environment = os.environ.get("APP_ENV", "development")
    config = DEFAULT_CONFIG.copy()
    config.update(load_yaml_config(environment))

    env_file = dotenv_values(CONFIG_DIR / ".env")
    for key, value in env_file.items():
        if value is not None:
            config[normalized_key(key)] = value

    for key, value in os.environ.items():
        if key.upper().startswith("APP_") and key.upper() != "APP_ENV":
            config[normalized_key(key)] = value

    for item in overrides or []:
        key, separator, value = item.partition("=")
        if not separator or not key.strip():
            raise HTTPException(
                status_code=422,
                detail="Each set parameter must use key=value format",
            )
        config[normalized_key(key)] = value

    result = {key: coerce_value(key, value) for key, value in config.items()}
    result["api_key"] = "****"
    return result


@app.get("/effective-config")
async def get_effective_config(set: list[str] | None = Query(default=None)):
    return effective_config(set)
