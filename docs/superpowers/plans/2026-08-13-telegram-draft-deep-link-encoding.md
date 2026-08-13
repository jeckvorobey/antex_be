# Telegram Draft Deep Link Encoding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Передавать предзаполненный текст Telegram chat deep link без искажения пробелов и Unicode на всех клиентах.

**Architecture:** `_chat_url_with_draft()` остаётся единой точкой сериализации `text` для URL `t.me` и `tg://resolve`. Она будет использовать стандартный `urllib.parse.urlencode` с `quote` как `quote_via`; тесты проверят raw URL и обратное декодирование.

**Tech Stack:** Python 3.13, aiogram 3, pytest, urllib.parse.

## Global Constraints

- Все изменения выполняются в `back/` и не меняют platform-specific логику.
- TDD: сначала падающий тест, затем минимальный production fix.
- Проверки выполняются только командами backend из `back/`.

---

### Task 1: Regression-тест сериализации черновика

**Files:**
- Modify: `tests/telegram/test_start_and_keyboards.py`
- Test: `tests/telegram/test_start_and_keyboards.py`

**Interfaces:**
- Consumes: `_chat_url_with_draft(chat_url: str, message_text: str | None) -> str`.
- Produces: проверка URL-контракта для `https://t.me/<username>` и `tg://resolve?domain=<username>`.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.parametrize("chat_url", ["https://t.me/manager", "tg://resolve?domain=manager"])
def test_chat_url_with_draft_percent_encodes_message_text(chat_url: str) -> None:
    message = "Привет мир 👋\\n& ? +"
    url = _chat_url_with_draft(chat_url, message)
    assert "%20" in url
    assert "+" not in urlparse(url).query
    assert parse_qs(urlparse(url).query)["text"] == [message]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/telegram/test_start_and_keyboards.py -k draft -v`
Expected: FAIL because current form-encoding serializes spaces as `+`.

- [ ] **Step 3: Extend assertions for reserved characters**

```python
assert "%2B" in url
assert "%26" in url
assert "%3F" in url
assert "%0A" in url
```

### Task 2: Минимальная production-правка

**Files:**
- Modify: `app/telegram/keyboards.py:5-36`
- Test: `tests/telegram/test_start_and_keyboards.py`

**Interfaces:**
- Consumes: словарь query, сформированный `parse_qsl`.
- Produces: `urlunparse` с percent-encoded query.

- [ ] **Step 1: Import `quote`**

```python
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse
```

- [ ] **Step 2: Use `quote_via` in both serialization branches**

```python
urlencode(query, quote_via=quote)
```

- [ ] **Step 3: Run focused regression test**

Run: `uv run pytest tests/telegram/test_start_and_keyboards.py -k draft -v`
Expected: PASS.

### Task 3: Полная верификация и OpenSpec

**Files:**
- Modify: `openspec/changes/fix-telegram-draft-deep-link-encoding/tasks.md`

**Interfaces:**
- Consumes: backend test suite и OpenSpec change artifacts.
- Produces: завершённые задачи и validated OpenSpec change.

- [ ] **Step 1: Run backend suite**

Run: `uv run pytest tests -v`
Expected: PASS без новых ошибок генерации кнопок, ссылок менеджера и Telegram заявок.

- [ ] **Step 2: Run style checks**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: PASS.

- [ ] **Step 3: Mark completed OpenSpec tasks and validate**

Run: `openspec validate --strict --all`
Expected: PASS.
