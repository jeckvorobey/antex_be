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


EXCHANGE_CITY_TEMPLATE = """<footer>{category}</footer>
<h2>📍 {title}</h2>
<p>{description}</p>
<hr/>
<h3>{options_title}</h3>
<p>{options_hint}</p>"""


EXCHANGE_SERVICE_TEMPLATE = """<footer>{category}</footer>
<h2>💎 {title}</h2>
<p>{description}</p>
<hr/>
<h3>{options_title}</h3>
<ul>
<li><b>🚕 {cash_delivery_title}</b><br/>{cash_delivery_description}</li>
<li><b>🏧 {cash_atm_title}</b><br/>{cash_atm_description}</li>
<li><b>💳 {bank_account_title}</b><br/>{bank_account_description}</li>
<li><b>🧰 {pay_services_title}</b><br/>{pay_services_description}</li>
</ul>"""


EXCHANGE_CURRENCY_TEMPLATE = """<footer>{category}</footer>
<h2>💱 {title}</h2>
<p>{description}</p>
<hr/>
<h3>{rates_title}</h3>
{rate_items}
<p>{options_hint}</p>"""


EXCHANGE_AMOUNT_TEMPLATE = """<footer>{step}</footer>
<h2>💱 {title}</h2>{rate_block}
<p>{prompt}</p>{minimum_block}"""


EXCHANGE_CONFIRM_TEMPLATE = """<footer>{step}</footer>
<h2>📋 {title}</h2>
{order_summary}
<p>{hint}</p>"""
