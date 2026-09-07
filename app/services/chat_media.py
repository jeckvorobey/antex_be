"""Безопасная нормализация браузерных записей для Telegram."""

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

MAX_RECORDING_BYTES = 20 * 1024 * 1024
MAX_VOICE_SECONDS = 300
MAX_VIDEO_NOTE_SECONDS = 60
MEDIA_TIMEOUT_SECONDS = 90
_MEDIA_SLOTS = asyncio.Semaphore(2)
# Исключены playlist/concat/image демультиплексоры и сетевые протоколы.
_INPUT_OPTIONS = [
    "-protocol_whitelist",
    "file",
    "-format_whitelist",
    "matroska,webm,mov,ogg,wav,mp3,flac,aac",
    "-probesize",
    "5000000",
    "-analyzeduration",
    "5000000",
]


@dataclass(frozen=True, slots=True)
class NormalizedRecording:
    content: bytes
    filename: str
    mime_type: str
    metadata: dict[str, object]


async def _run(*args: str) -> bytes:
    """Запустить без shell, ограничить время и объём stdout, убрать stderr."""
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        raise ValueError("recording_processor_unavailable") from None
    try:
        async with asyncio.timeout(MEDIA_TIMEOUT_SECONDS):
            assert process.stdout is not None
            output = bytearray()
            while chunk := await process.stdout.read(8192):
                output.extend(chunk)
                if len(output) > 65536:
                    raise ValueError("invalid_recording_media")
            await process.wait()
        if process.returncode:
            raise ValueError("invalid_recording_media")
        return bytes(output)
    except TimeoutError:
        raise ValueError("recording_processing_timeout") from None
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def _probe(path: Path) -> dict:
    output = await _run(
        "ffprobe",
        "-v",
        "error",
        *_INPUT_OPTIONS,
        "-show_entries",
        "format=duration:stream=codec_type,width,height,duration",
        "-of",
        "json",
        str(path),
    )
    try:
        return json.loads(output)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("invalid_recording_media") from None


def _duration(metadata: dict) -> float | None:
    durations = [metadata.get("format", {}).get("duration")]
    durations.extend(stream.get("duration") for stream in metadata.get("streams", []))
    values = []
    for value in durations:
        try:
            seconds = float(value)
            if math.isfinite(seconds) and seconds >= 0:
                values.append(seconds)
        except (TypeError, ValueError):
            continue
    return max(values) if values else None


async def normalize_recording(content: bytes, *, kind: str) -> NormalizedRecording:
    """Проверить лимиты и получить OGG/Opus либо квадратный MP4/H264/AAC."""
    if kind not in {"voice", "video_note"}:
        raise ValueError("unsupported_attachment_kind")
    if not content or len(content) > MAX_RECORDING_BYTES:
        raise ValueError("invalid_attachment_size")
    try:
        await asyncio.wait_for(_MEDIA_SLOTS.acquire(), timeout=10)
    except TimeoutError:
        raise ValueError("recording_processor_busy") from None
    try:
        return await _normalize(content, kind=kind)
    finally:
        _MEDIA_SLOTS.release()


async def _normalize(content: bytes, *, kind: str) -> NormalizedRecording:
    limit = MAX_VOICE_SECONDS if kind == "voice" else MAX_VIDEO_NOTE_SECONDS
    filename = "voice.ogg" if kind == "voice" else "video-note.mp4"
    with TemporaryDirectory(prefix="antex-recording-") as directory:
        source, target = Path(directory) / "input", Path(directory) / filename
        await asyncio.to_thread(source.write_bytes, content)
        metadata = await _probe(source)
        duration = _duration(metadata)
        if duration is not None and duration > limit + 0.05:
            raise ValueError("recording_duration_exceeded")
        streams = metadata.get("streams", [])
        required = "audio" if kind == "voice" else "video"
        if not any(stream.get("codec_type") == required for stream in streams):
            raise ValueError("invalid_recording_media")
        if any(max(stream.get("width", 0), stream.get("height", 0)) > 4096 for stream in streams):
            raise ValueError("invalid_recording_dimensions")
        options = [
            "-map",
            "0:a:0",
            "-vn",
            "-c:a",
            "libopus",
            "-b:a",
            "48k",
            "-ac",
            "1",
            "-ar",
            "48000",
        ]
        if kind == "video_note":
            options = [
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-vf",
                "crop=min(iw\\,ih):min(iw\\,ih),scale=384:384,setsar=1",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "30",
                "-b:v",
                "700k",
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-ac",
                "1",
                "-movflags",
                "+faststart",
            ]
        await _run(
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-y",
            *_INPUT_OPTIONS,
            "-threads",
            "1",
            "-i",
            str(source),
            "-t",
            str(limit + 1),
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            *options,
            "-threads",
            "1",
            "-filter_threads",
            "1",
            "-fs",
            str(MAX_RECORDING_BYTES + 1),
            str(target),
        )
        if target.stat().st_size > MAX_RECORDING_BYTES:
            raise ValueError("invalid_attachment_size")
        converted = await _probe(target)
        duration = _duration(converted)
        if duration is None or duration <= 0:
            raise ValueError("invalid_recording_media")
        if duration > limit + 0.05:
            raise ValueError("recording_duration_exceeded")
        result_metadata: dict[str, object] = {"duration": duration}
        if kind == "video_note":
            result_metadata["length"] = 384
        return NormalizedRecording(
            await asyncio.to_thread(target.read_bytes),
            filename,
            "audio/ogg" if kind == "voice" else "video/mp4",
            result_metadata,
        )
