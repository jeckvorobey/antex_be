"""Шаблоны Rich Messages для Telegram."""

EXCHANGE_START_TEMPLATE = """<p>👋 <b>{greeting}</b></p>
<footer>{category}</footer>
<h2>💱 {title}</h2>
<p>{description}</p>
<hr/>
<h3>📝 {instruction_title}</h3>
<p>{instruction}</p>{working_hours_block}{off_hours_block}"""

WORKING_HOURS_BLOCK_TEMPLATE = """

<blockquote>🕘 <b>{title}</b>
<b>{requests_anytime}</b>
{managers_label}: {hours}.</blockquote>"""

OFF_HOURS_BLOCK_TEMPLATE = """

<blockquote>⚠️ <b>{title}</b>
{text}</blockquote>"""
