from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Redis / Celery
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    # TTS defaults
    default_generator: str = "silero"
    default_speaker: str = "eugene"
    default_sample_rate: int = 48000

    # Storage
    temp_dir: str = "temp"
    file_ttl_minutes: int = 15

    # Netbird — этот воркер раздаёт файлы по своему Netbird IP
    netbird_ip: str = "127.0.0.1"
    file_server_port: int = 8888

    @property
    def file_base_url(self) -> str:
        return f"http://{self.netbird_ip}:{self.file_server_port}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def broker_url(self) -> str:
        if self.celery_broker_url:
            return self.celery_broker_url
        pwd = f":{self.redis_password}@" if self.redis_password else "@"
        return f"redis://{pwd}{self.redis_host}:{self.redis_port}/0"

    @property
    def result_backend(self) -> str:
        if self.celery_result_backend:
            return self.celery_result_backend
        pwd = f":{self.redis_password}@" if self.redis_password else "@"
        return f"redis://{pwd}{self.redis_host}:{self.redis_port}/1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
