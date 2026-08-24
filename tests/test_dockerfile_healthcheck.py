from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def test_backend_image_healthcheck_uses_python_without_apt_or_curl() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "apt-get" not in dockerfile
    assert "curl" not in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "urllib.request.urlopen" in dockerfile
    assert "http://127.0.0.1:8000/health" in dockerfile
