from __future__ import annotations

import pytest

from app.exceptions import AntExException


async def test_generator_supports_existing_eight_character_contract(monkeypatch) -> None:
    from app.core.unique_code import generate_unique_code

    monkeypatch.setattr("app.core.unique_code.secrets.choice", lambda alphabet: alphabet[0])

    code = await generate_unique_code(length=8, alphabet="ABC123", exists=lambda _: _false())

    assert code == "AAAAAAAA"


async def test_marketing_code_is_ten_uppercase_ascii_alphanumeric() -> None:
    from app.core.unique_code import generate_unique_code

    code = await generate_unique_code(
        length=10,
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        exists=lambda _: _false(),
    )

    assert len(code) == 10
    assert code.isascii()
    assert code.isalnum()
    assert code == code.upper()


async def test_generator_retries_collision(monkeypatch) -> None:
    from app.core.unique_code import generate_unique_code

    candidates = iter(["A", "B"])
    monkeypatch.setattr("app.core.unique_code.secrets.choice", lambda _: next(candidates))

    code = await generate_unique_code(
        length=1,
        alphabet="AB",
        exists=lambda value: _value(value == "A"),
        max_attempts=2,
    )

    assert code == "B"


async def test_generator_returns_machine_readable_error_after_exhaustion(monkeypatch) -> None:
    from app.core.unique_code import generate_unique_code

    monkeypatch.setattr("app.core.unique_code.secrets.choice", lambda _: "A")

    with pytest.raises(AntExException) as error:
        await generate_unique_code(
            length=10,
            alphabet="A",
            exists=lambda _: _value(True),
            max_attempts=2,
        )

    assert error.value.code == "UNIQUE_CODE_EXHAUSTED"
    assert error.value.status_code == 503


async def _false() -> bool:
    return False


async def _value(value: bool) -> bool:
    return value
