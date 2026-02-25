from flask import Flask
from ..extensions import mongo_client


def ensure_indexes(app: Flask):
    db = mongo_client.db(app)
    db.users.create_index("email", unique=True)