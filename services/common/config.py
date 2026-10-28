import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    task_id: str = os.getenv("IRIS_TASK_ID", "IRIS-SIG-47")
    source_base_url: str = os.getenv(
        "IRIS_SOURCE_BASE_URL", "https://www.institutional-money.com/news/"
    )
    http_timeout_seconds: int = int(os.getenv("IRIS_HTTP_TIMEOUT", "15"))
    http_max_retries: int = int(os.getenv("IRIS_HTTP_MAX_RETRIES", "3"))
    max_pages: int = int(os.getenv("IRIS_MAX_PAGES", "2"))
    user_agent: str = os.getenv(
        "IRIS_USER_AGENT",
        "IRIS-Harvester/1.0 (+https://github.com/amaurisantosjr/iris-sample; Task=IRIS-SIG-47)",
    )
    db_host: str = os.getenv("POSTGRES_HOST", "localhost")
    db_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    db_name: str = os.getenv("POSTGRES_DB", "iris")
    db_user: str = os.getenv("POSTGRES_USER", "")
    db_password: str = os.getenv("POSTGRES_PASSWORD", "")

    @property
    def postgres_dsn(self) -> str:
        if not self.db_user or not self.db_password:
            raise ValueError(
                "Database credentials (POSTGRES_USER, POSTGRES_PASSWORD) must be provided via environment variables."
            )
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


def get_settings() -> Settings:
    return Settings()
