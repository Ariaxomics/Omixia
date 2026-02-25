from dataclasses import dataclass
from flask import Flask
from pymongo import MongoClient
import redis
from flask_session import Session


@dataclass
class MongoExt:
    client: MongoClient | None = None

    def init_app(self, app: Flask) -> None:
        self.client = MongoClient(app.config["MONGO_URI"])

    def db(self, app: Flask):
        return self.client[app.config["OMIXIA_DB_NAME"]]


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