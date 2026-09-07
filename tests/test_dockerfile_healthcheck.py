from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def test_backend_image_supports_coolify_and_python_healthchecks() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    # Coolify требует curl, самостоятельный запуск использует Python.
    assert "apt-get install -y --no-install-recommends curl ffmpeg" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "urllib.request.urlopen" in dockerfile
    assert "http://127.0.0.1:8000/health" in dockerfile
