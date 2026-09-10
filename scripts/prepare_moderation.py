#!/usr/bin/env python3
"""Provisionne les poids publics figés ; aucun contenu utilisateur n'est envoyé.

À exécuter une fois après pip install, jamais depuis une route Flask.
"""
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.content_moderation import (  # noqa: E402
    MODEL_FILES, MODEL_REPOSITORY, MODEL_REVISION, file_digest, model_directory,
)


def main():
    directory = model_directory()
    directory.mkdir(parents=True, exist_ok=True)
    for name, (remote, digest) in MODEL_FILES.items():
        target = directory / name
        if target.is_file() and file_digest(target) == digest:
            continue
        url = f"https://huggingface.co/{MODEL_REPOSITORY}/resolve/{MODEL_REVISION}/{remote}"
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
            temporary = Path(output.name)
            try:
                with urllib.request.urlopen(url, timeout=30) as response:
                    for chunk in iter(lambda: response.read(1024 * 1024), b""):
                        output.write(chunk)
                output.close()
                if file_digest(temporary) != digest:
                    raise RuntimeError("Empreinte du modèle local invalide.")
                temporary.chmod(0o644)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
    print("Modèle de modération local installé et empreintes vérifiées.")


if __name__ == "__main__":
    main()
