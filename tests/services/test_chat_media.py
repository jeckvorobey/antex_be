from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from app.services.chat_media import normalize_recording


@pytest.mark.parametrize(
    "kind,container",
    [("voice", "webm"), ("voice", "mp4"), ("video_note", "webm"), ("video_note", "mp4")],
)
async def test_browser_recordings_become_native_telegram_media(tmp_path, kind, container):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg не установлен")
    source = tmp_path / f"source.{container}"
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=s=320x240:r=10",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=500",
        "-t",
        "0.5",
        "-threads",
        "1",
    ]
    command += (
        ["-c:v", "libvpx", "-c:a", "libopus"]
        if container == "webm"
        else ["-c:v", "libx264", "-c:a", "aac"]
    )
    subprocess.run([*command, str(source)], check=True, capture_output=True, timeout=20)
    result = await normalize_recording(source.read_bytes(), kind=kind)
    output = tmp_path / result.filename
    output.write_bytes(result.content)
    metadata = json.loads(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)], timeout=10
        )
    )
    streams = metadata["streams"]
    assert result.metadata["duration"] > 0
    if kind == "voice":
        assert [stream["codec_name"] for stream in streams] == ["opus"]
        assert result.mime_type == "audio/ogg"
    else:
        assert {stream["codec_name"] for stream in streams} == {"h264", "aac"}
        video = next(stream for stream in streams if stream["codec_type"] == "video")
        assert video["width"] == video["height"] == 384


async def test_invalid_media_and_limits_are_machine_errors():
    with pytest.raises(ValueError, match="invalid_recording_media"):
        await normalize_recording(b"not media", kind="voice")
    with pytest.raises(ValueError, match="invalid_attachment_size"):
        await normalize_recording(b"x" * (20 * 1024 * 1024 + 1), kind="voice")


async def test_recording_duration_is_rejected(tmp_path, monkeypatch):
    source = tmp_path / "long.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=500",
            "-t",
            "1",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )
    monkeypatch.setattr("app.services.chat_media.MAX_VOICE_SECONDS", 0.1)
    with pytest.raises(ValueError, match="recording_duration_exceeded"):
        await normalize_recording(source.read_bytes(), kind="voice")
