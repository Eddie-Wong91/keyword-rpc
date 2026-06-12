from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_dir: Path = Field(default=BASE_DIR / "logs", alias="LOG_DIR")

    rpc_host: str = Field(default="0.0.0.0", alias="RPC_HOST")
    rpc_port: int = Field(default=5001, alias="RPC_PORT")
    rpc_debug: bool = Field(default=False, alias="RPC_DEBUG")
    rpc_url: str = Field(default="http://127.0.0.1:5001/rpc", alias="RPC_URL")

    request_timeout: int = Field(default=60, alias="REQUEST_TIMEOUT")
    batch_request_interval_seconds: int = Field(default=1, alias="BATCH_REQUEST_INTERVAL_SECONDS")
    sif_retry_count: int = Field(default=10, alias="SIF_RETRY_COUNT")
    sif_retry_sleep_seconds: int = Field(default=2, alias="SIF_RETRY_SLEEP_SECONDS")

    excel_base_dir: Path = Field(default=Path(r"C:\rpa\amazon\product_info"), alias="EXCEL_BASE_DIR")

    uuid_resource_variable_url: str = Field(alias="UUID_RESOURCE_VARIABLE_URL")
    uuid_resource_variable_uuid: str = Field(alias="UUID_RESOURCE_VARIABLE_UUID")
    uuid_app_key: str = Field(alias="UUID_APP_KEY")
    uuid_app_secret: str = Field(alias="UUID_APP_SECRET")

    lingxing_api_base_url: str = Field(alias="LINGXING_API_BASE_URL")
    lingxing_referer: str = Field(alias="LINGXING_REFERER")

    sif_api_base_url: str = Field(default="https://www.sif.com", alias="SIF_API_BASE_URL")
    sif_origin: str = Field(default="https://www.sif.com", alias="SIF_ORIGIN")
    sif_user_agent: str = Field(alias="SIF_USER_AGENT")

    local_db_host: str = Field(default="localhost", alias="LOCAL_DB_HOST")
    local_db_port: int = Field(default=3306, alias="LOCAL_DB_PORT")
    local_db_user: str = Field(alias="LOCAL_DB_USER")
    local_db_password: str = Field(alias="LOCAL_DB_PASSWORD")
    local_db_database: str = Field(alias="LOCAL_DB_DATABASE")

    sif_db_host: str = Field(default="localhost", alias="SIF_DB_HOST")
    sif_db_port: int = Field(default=3306, alias="SIF_DB_PORT")
    sif_db_user: str = Field(alias="SIF_DB_USER")
    sif_db_password: str = Field(alias="SIF_DB_PASSWORD")
    sif_db_database: str = Field(alias="SIF_DB_DATABASE")

    lingxing_db_port: int = Field(default=3306, alias="LINGXING_DB_PORT")
    lingxing_db_user: str = Field(alias="LINGXING_DB_USER")
    lingxing_db_password: str = Field(alias="LINGXING_DB_PASSWORD")
    lingxing_db_database: str = Field(alias="LINGXING_DB_DATABASE")


settings = Settings()


def require_env(*names: str) -> None:
    missing = []
    for name in names:
        field_name = name.lower()
        if not hasattr(settings, field_name) or not getattr(settings, field_name):
            missing.append(name)
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


LOG_DIR = settings.log_dir

RPC_HOST = settings.rpc_host
RPC_PORT = settings.rpc_port
RPC_DEBUG = settings.rpc_debug
RPC_URL = settings.rpc_url

REQUEST_TIMEOUT = settings.request_timeout
BATCH_REQUEST_INTERVAL_SECONDS = settings.batch_request_interval_seconds
SIF_RETRY_COUNT = settings.sif_retry_count
SIF_RETRY_SLEEP_SECONDS = settings.sif_retry_sleep_seconds

EXCEL_BASE_DIR = settings.excel_base_dir

UUID_RESOURCE_VARIABLE_URL = settings.uuid_resource_variable_url
UUID_RESOURCE_VARIABLE_UUID = settings.uuid_resource_variable_uuid
UUID_APP_KEY = settings.uuid_app_key
UUID_APP_SECRET = settings.uuid_app_secret

LINGXING_API_BASE_URL = settings.lingxing_api_base_url
LINGXING_REFERER = settings.lingxing_referer

SIF_API_BASE_URL = settings.sif_api_base_url
SIF_ORIGIN = settings.sif_origin
SIF_USER_AGENT = settings.sif_user_agent


def build_excel_path(group_name: str) -> Path:
    return EXCEL_BASE_DIR / f"{group_name}.xlsx"


def get_local_db_config() -> dict:
    return {
        "host": settings.local_db_host,
        "port": settings.local_db_port,
        "user": settings.local_db_user,
        "password": settings.local_db_password,
        "database": settings.local_db_database,
        "charset": "utf8mb4",
    }


def get_sif_db_config() -> dict:
    return {
        "host": settings.sif_db_host,
        "port": settings.sif_db_port,
        "user": settings.sif_db_user,
        "password": settings.sif_db_password,
        "database": settings.sif_db_database,
        "charset": "utf8mb4",
    }


def get_lingxing_db_config(ipaddr: str) -> dict:
    return {
        "host": ipaddr,
        "port": settings.lingxing_db_port,
        "user": settings.lingxing_db_user,
        "password": settings.lingxing_db_password,
        "database": settings.lingxing_db_database,
        "charset": "utf8mb4",
    }
