from dataclasses import dataclass

import redis
from pymongo import MongoClient

from src.config import settings


@dataclass
class MongoExt:
    client: MongoClient | None = None
    db_name: str | None = None

    def init_app(self) -> None:
        self.client = MongoClient(settings.MONGO_URI)
        self.db_name = settings.OMIXIA_DB_NAME

    @property
    def db(self):
        return self.client[self.db_name]


@dataclass
class RedisExt:
    r: redis.Redis | None = None

    def init_app(self) -> None:
        self.r = redis.from_url(settings.CACHE_REDIS_URL, decode_responses=True)


mongo_client = MongoExt()
redis_client = RedisExt()
