import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME")
    DEBUG = bool(int(os.getenv("FLASK_DEBUG", "0")))

    MONGO_URI = os.getenv("MONGO_URI")
    OMIXIA_DB_NAME = os.getenv("OMIXIA_DB_NAME")

    CACHE_REDIS_URL = os.getenv("CACHE_REDIS_URL")
    REPORTS_BASE_PATH = os.getenv("REPORTS_BASE_PATH")

    DEVELOPMENT = bool(int(os.getenv("DEVELOPMENT", "0")))
    TESTING = bool(int(os.getenv("TESTING", "0")))