import atexit
import io
import logging
import os
import signal
from pathlib import Path

from flask import Flask, Request, render_template

from app.db import init_db
from app.execution_log import configure_execution_log, log_event

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_signal_handlers_installed = False


class InMemoryUploadRequest(Request):
    def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):
        # La limite globale de 2 Mio borne le parseur multipart ; aucun fichier
        # utilisateur n'est spoulé sur disque avant sa modération.
        return io.BytesIO()


def _install_signal_handlers() -> None:
    # Intercepte SIGTERM/SIGINT (ceux que Docker/l'utilisateur envoient pour un
    # arret propre) pour journaliser l'instant exact avant de laisser le
    # comportement normal se poursuivre. Ne fait rien pour SIGKILL, que rien
    # ne peut intercepter : le journal montrera alors une absence de trace,
    # pas une ligne d'arret.
    global _signal_handlers_installed
    if _signal_handlers_installed:
        return
    _signal_handlers_installed = True

    previous_handlers = {}

    def _handle_signal(signum, frame):
        log_event(
            "shutdown_signal_received",
            level=logging.WARNING,
            signal=signal.Signals(signum).name,
            pid=os.getpid(),
        )
        signal.signal(signum, previous_handlers[signum])
        os.kill(os.getpid(), signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[sig] = signal.signal(sig, _handle_signal)

    def _log_process_exit():
        # A la fermeture de Python, le fichier de log peut deja etre ferme
        # (notamment en test, ou plusieurs apps se creent/detruisent dans le
        # meme processus) : on l'ignore plutot que de polluer la sortie.
        try:
            log_event("process_exit", pid=os.getpid())
        except Exception:
            pass

    atexit.register(_log_process_exit)


def create_app(database_path: str | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )
    app.request_class = InMemoryUploadRequest
    app.config["DATABASE_PATH"] = database_path or os.environ.get(
        "DATABASE_PATH", "data/data.db"
    )

    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    init_db(app.config["DATABASE_PATH"])

    # Le journal d'execution vit a cote de la base (meme volume Docker),
    # sauf si EXECUTION_LOG_PATH est explicitement fourni.
    log_path = os.environ.get("EXECUTION_LOG_PATH") or str(
        Path(app.config["DATABASE_PATH"]).parent / "execution.log"
    )
    configure_execution_log(log_path)
    app.config["EXECUTION_LOG_PATH"] = log_path
    log_event("app_created", pid=os.getpid())
    _install_signal_handlers()

    @app.get("/")
    def index():
        return render_template("index.html")

    from app.routes import bp

    app.register_blueprint(bp)

    return app
