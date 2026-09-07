import os

from flask import Flask

from app.db import init_db


def create_app(database_path: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DATABASE_PATH"] = database_path or os.environ.get(
        "DATABASE_PATH", "data.db"
    )

    init_db(app.config["DATABASE_PATH"])

    from app.routes import bp

    app.register_blueprint(bp)

    return app
