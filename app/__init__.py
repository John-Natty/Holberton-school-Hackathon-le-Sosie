import os
from pathlib import Path

from flask import Flask, render_template

from app.db import init_db

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app(database_path: str | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )
    app.config["DATABASE_PATH"] = database_path or os.environ.get(
        "DATABASE_PATH", "data/data.db"
    )

    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    init_db(app.config["DATABASE_PATH"])

    @app.get("/")
    def index():
        return render_template("index.html")

    from app.routes import bp

    app.register_blueprint(bp)

    return app
