from dataclasses import dataclass
from flask import Flask
from pymongo import MongoClient
import redis
from flask_session import Session


@dataclass
class MongoExt:
    client: MongoClient | None = None
    db_name: str | None = None

    def init_app(self, app: Flask) -> None:
        self.client = MongoClient(app.config["MONGO_URI"])
        self.db_name = app.config["OMIXIA_DB_NAME"]

    @property
    def db(self):
        return self.client[self.db_name]


@dataclass
class RedisExt:
    r: redis.Redis | None = None

    def init_app(self, app: Flask) -> None:
        self.r = redis.from_url(app.config["CACHE_REDIS_URL"], decode_responses=True)


mongo_client = MongoExt()
redis_client = RedisExt()


def init_session(app: Flask) -> None:
    app.config["SESSION_TYPE"] = "redis"
    app.config["SESSION_REDIS"] = redis.from_url(app.config["CACHE_REDIS_URL"])
    Session(app)