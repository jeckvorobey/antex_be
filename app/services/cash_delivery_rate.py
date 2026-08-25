"""Политика эффективного курса доставки наличных."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_EVEN, Decimal

from app.enums.order import MethodGet
from app.exceptions import AntExException
from app.models.rate import Rate

CASH_DELIVERY_USDT_AMOUNT = Decimal("10")
CASH_DELIVERY_THRESHOLDS = {"RUB": 100_000, "USDT": 1_200}
MONEY_QUANTUM = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class CashDeliveryRateResult:
    """Сумма quote и внутренний курс доставки для сохранения в заявке."""

    amount_buy: float
    delivery_rate: float | None


class CashDeliveryRatePolicy:
    """Изолирует правило курса доставки от transport и persistence слоёв."""

    def calculate(
        self,
        rates: list[Rate],
        *,
        method_get: MethodGet | str | None,
        currency_sell: str,
        currency_buy: str,
        amount_sell: int,
        base_rate: float,
    ) -> CashDeliveryRateResult:
        """Рассчитывает итог и точный прямой курс без раскрытия внутренней суммы."""
        if base_rate <= 0:
            raise _rate_unavailable()

        amount_buy = round(amount_sell * base_rate, 2)
        if method_get != MethodGet.CASH:
            return CashDeliveryRateResult(amount_buy=amount_buy, delivery_rate=None)

        normalized_sell = currency_sell.upper()
        threshold = CASH_DELIVERY_THRESHOLDS.get(normalized_sell)
        if threshold is None or amount_sell >= threshold:
            return CashDeliveryRateResult(amount_buy=amount_buy, delivery_rate=base_rate)

        normalized_buy = currency_buy.upper()
        conversion_rate = next(
            (rate for rate in rates if rate.currency.upper() == f"USDT{normalized_buy}"),
            None,
        )
        if conversion_rate is None:
            raise _rate_unavailable()

        # `ceil` чувствителен к двоичной погрешности float: маржу применяем
        # непосредственно к десятичным значениям, доступным из модели курса.
        usdt_buy_rate = Decimal(str(conversion_rate.price)) * (
            Decimal("1") - Decimal(str(conversion_rate.margin)) / Decimal("100")
        )
        if usdt_buy_rate <= 0:
            raise _rate_unavailable()

        amount_decimal = Decimal(amount_sell)
        gross_amount = (amount_decimal * Decimal(str(base_rate))).quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_EVEN,
        )
        internal_equivalent = (CASH_DELIVERY_USDT_AMOUNT * usdt_buy_rate).to_integral_value(
            rounding=ROUND_CEILING
        )
        net_amount = gross_amount - internal_equivalent
        if net_amount <= 0:
            raise _rate_unavailable()

        delivery_rate = net_amount / amount_decimal
        authoritative_amount = (amount_decimal * delivery_rate).quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_EVEN,
        )
        return CashDeliveryRateResult(
            amount_buy=float(authoritative_amount),
            delivery_rate=float(delivery_rate),
        )


def _rate_unavailable() -> AntExException:
    return AntExException(
        "Rate is unavailable",
        code="RATE_UNAVAILABLE",
        status_code=503,
    )
