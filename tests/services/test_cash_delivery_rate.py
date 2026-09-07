"""Регрессии эффективного курса доставки наличных."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal

import pytest

from app.enums.country import Country
from app.enums.order import MethodGet
from app.exceptions import AntExError
from app.models.rate import Rate
from app.services.cash_delivery_rate import CashDeliveryRatePolicy
from app.services.exchange import CANONICAL_BUY_CURRENCIES


def _rate(currency: str, price: float, margin: float = 0.0) -> Rate:
    stamp = datetime(2026, 8, 15, tzinfo=UTC)
    return Rate(
        currency=currency,
        price=price,
        margin=margin,
        country=Country.THAILAND,
        createdAt=stamp,
        updatedAt=stamp,
    )


@pytest.mark.parametrize(
    ("currency_sell", "amount_sell", "expected_rate", "expected_amount"),
    [
        ("RUB", 99_999, 0.396369963699637, 39_636.6),
        ("RUB", 100_000, 0.4, 40_000.0),
        ("RUB", 100_001, 0.4, 40_000.4),
        ("USDT", 1_199, 35.89824854045038, 43_042.0),
        ("USDT", 1_200, 36.201, 43_441.2),
        ("USDT", 1_201, 36.201, 43_477.4),
    ],
)
def test_cash_delivery_rate_respects_rub_and_usdt_thresholds(
    currency_sell: str,
    amount_sell: int,
    expected_rate: float,
    expected_amount: float,
) -> None:
    """Сдвиг порога или применение правила на самом пороге изменит ожидаемый итог."""
    result = CashDeliveryRatePolicy().calculate(
        [_rate("USDTTHB", 36.201)],
        method_get=MethodGet.CASH,
        currency_sell=currency_sell,
        currency_buy="THB",
        amount_sell=amount_sell,
        base_rate=0.4 if currency_sell == "RUB" else 36.201,
    )

    assert result.delivery_rate == pytest.approx(expected_rate)
    assert result.amount_buy == pytest.approx(expected_amount)


@pytest.mark.parametrize(
    ("method_get", "expected_delivery_rate"),
    [
        (None, None),
        (MethodGet.QRCODE, None),
        (MethodGet.BANK_ACCOUNT, None),
        (MethodGet.PAY_SERVICES, None),
    ],
)
def test_non_cash_methods_keep_baseline_amount_and_no_delivery_rate(
    method_get: MethodGet | None,
    expected_delivery_rate: None,
) -> None:
    """Ошибочная активация cash-политики сломает остальные способы получения."""
    result = CashDeliveryRatePolicy().calculate(
        [],
        method_get=method_get,
        currency_sell="RUB",
        currency_buy="THB",
        amount_sell=25_000,
        base_rate=0.4,
    )

    assert result.delivery_rate is expected_delivery_rate
    assert result.amount_buy == pytest.approx(10_000.0)


def test_atxg_cash_keeps_existing_rate_without_commercial_adjustment() -> None:
    """ATXG не получает вычет, но любой cash сохраняет deliveryRate."""
    result = CashDeliveryRatePolicy().calculate(
        [],
        method_get=MethodGet.CASH,
        currency_sell="ATXG",
        currency_buy="THB",
        amount_sell=100,
        base_rate=36.2,
    )

    assert result.delivery_rate == pytest.approx(36.2)
    assert result.amount_buy == pytest.approx(3_620.0)


@pytest.mark.parametrize(
    ("currency_buy", "fee_rate", "base_rate", "expected_rate", "expected_amount"),
    [
        ("THB", 36.201, 0.4, 0.3637, 3_637.0),
        ("GEL", 2.601, 0.4, 0.3973, 3_973.0),
        ("VND", 26_000.01, 280.0, 253.9999, 2_539_999.0),
    ],
)
def test_cash_delivery_rate_uses_selected_receive_currency(
    currency_buy: str,
    fee_rate: float,
    base_rate: float,
    expected_rate: float,
    expected_amount: float,
) -> None:
    """Использование чужой USDT-пары даст неверный курс валюты получения."""
    result = CashDeliveryRatePolicy().calculate(
        [_rate(f"USDT{currency_buy}", fee_rate)],
        method_get=MethodGet.CASH,
        currency_sell="RUB",
        currency_buy=currency_buy,
        amount_sell=10_000,
        base_rate=base_rate,
    )

    assert result.delivery_rate == pytest.approx(expected_rate)
    assert result.amount_buy == pytest.approx(expected_amount)


@pytest.mark.parametrize(
    ("fee_price", "fee_margin", "expected_rate", "expected_amount"),
    [
        (36.2, 0.0, 0.38552, 9_638.0),
        (36.201, 0.0, 0.38548, 9_637.0),
        (36.2, 3.0, 0.38592, 9_648.0),
    ],
)
def test_cash_delivery_rate_rounds_up_after_applying_margin(
    fee_price: float,
    fee_margin: float,
    expected_rate: float,
    expected_amount: float,
) -> None:
    """Округление до маржи или добавление единицы к целому изменит результат."""
    result = CashDeliveryRatePolicy().calculate(
        [_rate("USDTTHB", fee_price, fee_margin)],
        method_get=MethodGet.CASH,
        currency_sell="RUB",
        currency_buy="THB",
        amount_sell=25_000,
        base_rate=0.4,
    )

    assert result.delivery_rate == pytest.approx(expected_rate)
    assert result.amount_buy == pytest.approx(expected_amount)


def test_exact_delivery_rate_reproduces_authoritative_amount() -> None:
    """Преждевременное округление deliveryRate сломает точный amountBuy."""
    result = CashDeliveryRatePolicy().calculate(
        [_rate("USDTTHB", 36.201)],
        method_get=MethodGet.CASH,
        currency_sell="RUB",
        currency_buy="THB",
        amount_sell=12_345,
        base_rate=0.4,
    )

    assert result.delivery_rate == pytest.approx(0.37059538274605097)
    assert result.amount_buy == pytest.approx(4_575.0)
    assert round(12_345 * result.delivery_rate, 2) == result.amount_buy
    assert result.delivery_rate < 0.4


@pytest.mark.parametrize("invalid_rate", [None, 0.0, -1.0])
def test_applicable_cash_rejects_missing_or_non_positive_conversion_rate(
    invalid_rate: float | None,
) -> None:
    """Недоступная зависимая пара не должна молча отключать внутреннее правило."""
    rates = [] if invalid_rate is None else [_rate("USDTTHB", invalid_rate)]

    with pytest.raises(AntExError) as error:
        CashDeliveryRatePolicy().calculate(
            rates,
            method_get=MethodGet.CASH,
            currency_sell="RUB",
            currency_buy="THB",
            amount_sell=25_000,
            base_rate=0.4,
        )

    assert error.value.code == "RATE_UNAVAILABLE"
    assert error.value.status_code == 503
    assert error.value.params == {}


def test_applicable_cash_rejects_non_positive_result() -> None:
    """Неположительный итог не должен превращаться в заявку или скрытый ноль."""
    with pytest.raises(AntExError) as error:
        CashDeliveryRatePolicy().calculate(
            [_rate("USDTTHB", 36.201)],
            method_get=MethodGet.CASH,
            currency_sell="RUB",
            currency_buy="THB",
            amount_sell=1,
            base_rate=0.4,
        )

    assert error.value.code == "RATE_UNAVAILABLE"
    assert error.value.params == {}


RUB_CASH_MATRIX = (
    # Валюта получения, точный исходный курс, USDT price/margin и cash-вычет.
    ("THB", 0.4, 36.201, 3.0, 352),
    ("GEL", 0.0291, 2.601, 3.0, 26),
    ("VND", 298.8190358473305, 27334.45652173913, 8.0, 251_477),
)


def test_cash_matrix_explicitly_covers_all_canonical_rub_pairs() -> None:
    """Новая каноническая RUB-пара требует отдельной строки cash-матрицы."""
    assert {currency_buy for currency_buy, *_ in RUB_CASH_MATRIX} == CANONICAL_BUY_CURRENCIES


@pytest.mark.parametrize(
    (
        "currency_buy,base_rate,conversion_price,conversion_margin,expected_fee,amount_sell,"
        "expected_amount,expected_delivery_rate"
    ),
    [
        ("THB", 0.4, 36.201, 3.0, 352, 25_000, 9_648.0, 0.38592),
        ("THB", 0.4, 36.201, 3.0, 352, 99_999, 39_647.6, 0.396479964799648),
        ("THB", 0.4, 36.201, 3.0, 352, 100_000, 40_000.0, 0.4),
        ("GEL", 0.0291, 2.601, 3.0, 26, 25_000, 701.5, 0.02806),
        ("GEL", 0.0291, 2.601, 3.0, 26, 99_999, 2_883.97, 0.028839988399884),
        ("GEL", 0.0291, 2.601, 3.0, 26, 100_000, 2_910.0, 0.0291),
        (
            "VND",
            298.8190358473305,
            27334.45652173913,
            8.0,
            251_477,
            25_000,
            7_218_998.9,
            288.759956,
        ),
        (
            "VND",
            298.8190358473305,
            27334.45652173913,
            8.0,
            251_477,
            99_999,
            29_630_127.77,
            296.3042407424074,
        ),
        (
            "VND",
            298.8190358473305,
            27334.45652173913,
            8.0,
            251_477,
            100_000,
            29_881_903.58,
            298.8190358,
        ),
    ],
)
def test_cash_delivery_rate_rub_matrix(
    currency_buy: str,
    base_rate: float,
    conversion_price: float,
    conversion_margin: float,
    expected_fee: int,
    amount_sell: int,
    expected_amount: float,
    expected_delivery_rate: float,
) -> None:
    """Матрица фиксирует маржу, ceil, порог и эффективный курс каждой RUB-пары."""
    conversion_rate = _rate(f"USDT{currency_buy}", conversion_price, conversion_margin)
    result = CashDeliveryRatePolicy().calculate(
        [conversion_rate],
        method_get=MethodGet.CASH,
        currency_sell="RUB",
        currency_buy=currency_buy,
        amount_sell=amount_sell,
        base_rate=base_rate,
    )

    effective_conversion_rate = Decimal(str(conversion_price)) * (
        Decimal("1") - Decimal(str(conversion_margin)) / Decimal("100")
    )
    assert (Decimal("10") * effective_conversion_rate).to_integral_value(
        rounding=ROUND_CEILING
    ) == expected_fee
    assert result.amount_buy == pytest.approx(expected_amount)
    assert result.delivery_rate == pytest.approx(expected_delivery_rate)


def test_cash_delivery_rate_vnd_order_regression() -> None:
    """Зафиксированная заявка VND использует точный исходный курс, но не display-курс."""
    result = CashDeliveryRatePolicy().calculate(
        [_rate("USDTVND", 27334.45652173913, 8.0)],
        method_get=MethodGet.CASH,
        currency_sell="RUB",
        currency_buy="VND",
        amount_sell=25_000,
        base_rate=298.8190358473305,
    )

    assert result.amount_buy == pytest.approx(7_218_998.90)
    assert result.delivery_rate == pytest.approx(288.759956)


@pytest.mark.parametrize(
    ("price", "margin", "expected_fee"),
    [(2.5, 8.0, 23), (2.5, 0.0, 25)],
)
def test_cash_delivery_rate_ceil_uses_exact_decimal_margin(
    price: float,
    margin: float,
    expected_fee: int,
) -> None:
    """Float-погрешность после маржи не должна добавлять валютную единицу к ceil."""
    result = CashDeliveryRatePolicy().calculate(
        [_rate("USDTTHB", price, margin)],
        method_get=MethodGet.CASH,
        currency_sell="RUB",
        currency_buy="THB",
        amount_sell=25_000,
        base_rate=1.0,
    )

    assert result.amount_buy == pytest.approx(25_000 - expected_fee)
    assert result.delivery_rate == pytest.approx((25_000 - expected_fee) / 25_000)


@pytest.mark.parametrize("currency_buy", sorted(CANONICAL_BUY_CURRENCIES))
@pytest.mark.parametrize(
    "conversion_price,conversion_margin", [(0.0, 0.0), (-1.0, 0.0), (2.5, 100.0)]
)
def test_every_canonical_rub_pair_rejects_invalid_conversion_rate(
    currency_buy: str,
    conversion_price: float,
    conversion_margin: float,
) -> None:
    """Каждая каноническая RUB-пара нейтрально отвергает нулевую conversion-пару."""
    with pytest.raises(AntExError) as error:
        CashDeliveryRatePolicy().calculate(
            [_rate(f"USDT{currency_buy}", conversion_price, conversion_margin)],
            method_get=MethodGet.CASH,
            currency_sell="RUB",
            currency_buy=currency_buy,
            amount_sell=25_000,
            base_rate=1.0,
        )

    assert error.value.code == "RATE_UNAVAILABLE"
