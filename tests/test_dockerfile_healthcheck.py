from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def test_backend_image_healthcheck_uses_standard_python_without_curl() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    # ffmpeg устанавливается для медиа чата; healthcheck не требует curl.
    assert "curl" not in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "urllib.request.urlopen" in dockerfile
    assert "http://127.0.0.1:8000/health" in dockerfile
