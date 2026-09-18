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
AMOUNT_SELL_QUANTUM = Decimal("0.00000001")


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
        amount_sell: Decimal,
        base_rate: float,
    ) -> CashDeliveryRateResult:
        """Рассчитывает итог и точный прямой курс без раскрытия внутренней суммы."""
        if base_rate <= 0:
            raise _rate_unavailable()

        amount_decimal = Decimal(str(amount_sell))
        rate_decimal = Decimal(str(base_rate))
        amount_buy = (amount_decimal * rate_decimal).quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_EVEN,
        )
        if method_get != MethodGet.CASH:
            return CashDeliveryRateResult(amount_buy=float(amount_buy), delivery_rate=None)

        normalized_sell = currency_sell.upper()
        threshold = CASH_DELIVERY_THRESHOLDS.get(normalized_sell)
        if threshold is None or amount_decimal >= threshold:
            return CashDeliveryRateResult(amount_buy=float(amount_buy), delivery_rate=base_rate)

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

        gross_amount = (amount_decimal * rate_decimal).quantize(
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

    def calculate_amount_sell(
        self,
        rates: list[Rate],
        *,
        method_get: MethodGet | str | None,
        currency_sell: str,
        currency_buy: str,
        amount_buy: Decimal,
        base_rate: float,
    ) -> Decimal:
        """Обращает действующую policy и подтверждает результат прямым расчётом."""
        rate_decimal = Decimal(str(base_rate))
        if rate_decimal <= 0 or amount_buy <= 0:
            raise _rate_unavailable()

        fee = Decimal("0")
        threshold = CASH_DELIVERY_THRESHOLDS.get(currency_sell.upper())
        if method_get == MethodGet.CASH and threshold is not None:
            conversion_rate = next(
                (rate for rate in rates if rate.currency.upper() == f"USDT{currency_buy.upper()}"),
                None,
            )
            if conversion_rate is None:
                raise _rate_unavailable()
            usdt_buy_rate = Decimal(str(conversion_rate.price)) * (
                Decimal("1") - Decimal(str(conversion_rate.margin)) / Decimal("100")
            )
            fee = (CASH_DELIVERY_USDT_AMOUNT * usdt_buy_rate).to_integral_value(
                rounding=ROUND_CEILING
            )

        amount_sell = ((amount_buy + fee) / rate_decimal).quantize(
            AMOUNT_SELL_QUANTUM,
            rounding=ROUND_HALF_EVEN,
        )
        if method_get == MethodGet.CASH and threshold is not None and amount_sell >= threshold:
            amount_sell = (amount_buy / rate_decimal).quantize(
                AMOUNT_SELL_QUANTUM,
                rounding=ROUND_HALF_EVEN,
            )

        verified = self.calculate(
            rates,
            method_get=method_get,
            currency_sell=currency_sell,
            currency_buy=currency_buy,
            amount_sell=amount_sell,
            base_rate=base_rate,
        )
        if Decimal(str(verified.amount_buy)).quantize(MONEY_QUANTUM) != amount_buy.quantize(
            MONEY_QUANTUM
        ):
            raise _amount_not_representable()
        return amount_sell


def _amount_not_representable() -> AntExException:
    return AntExException(
        "Requested amount cannot be represented with available rate",
        code="AMOUNT_NOT_REPRESENTABLE",
        status_code=422,
    )


def _rate_unavailable() -> AntExException:
    return AntExException(
        "Rate is unavailable",
        code="RATE_UNAVAILABLE",
        status_code=503,
    )
