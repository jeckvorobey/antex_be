"""HTML-шаблоны сообщений Telegram.

Разметка находится отдельно от локализованных текстов, чтобы все языки
использовали одну проверяемую структуру обычного Telegram HTML.
"""

EXCHANGE_START_TEMPLATE = """👋 {greeting}

<b>💱 {title}</b>

{description}

📝 <b>{instruction_title}</b>
{instruction}{working_hours_block}{off_hours_block}"""

WORKING_HOURS_BLOCK_TEMPLATE = """

<blockquote>🕘 <b>{title}</b>
<b>{requests_anytime}</b>
{managers_label}: {hours}.</blockquote>"""

OFF_HOURS_BLOCK_TEMPLATE = """

<blockquote>⚠️ <b>{title}</b>
{text}</blockquote>"""
