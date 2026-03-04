from flask import Flask
from src.config import Config
from src.extensions import mongo_client, redis_client, init_session
from src.blueprints.api_v1.routes import api_bp
from src.blueprints.web.routes import web_bp
from src.db.indexes import ensure_indexes
from src.cli.load_demo import load_demo_data
from src.cli.create_user import register_create_user_command


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config())

    mongo_client.init_app(app)
    redis_client.init_app(app)
    init_session(app)

    @app.cli.command("load-demo")
    def load_demo():
        load_demo_data(app)

    register_create_user_command(app)

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(web_bp)

    try:
        with app.app_context():
            ensure_indexes(app)
    except Exception as e:
        print(f"Mongo not ready yet: {e}")
    return app


