from flask import Flask
from .config import Config
from .extensions import mongo_client, redis_client, init_session
from .blueprints.api.routes import api_bp
from .blueprints.web.routes import web_bp
from .db.indexes import ensure_indexes



def create_app():
    app = Flask(__name__)
    app.config.from_object(Config())

    mongo_client.init_app(app)
    redis_client.init_app(app)
    init_session(app)

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(web_bp)

    try:
        with app.app_context():
            ensure_indexes(app)
    except Exception as e:
        print(f"Mongo not ready yet: {e}")
    return app


