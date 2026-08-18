from __future__ import annotations

from app.api.routers.manager import update_manager_order_status
from app.enums.country import Country
from app.enums.order import OrderStatus
from app.enums.user import UserRole
from app.models.order import Order
from app.models.user import User
from app.schemas.chat import ManagerOrderStatusRequest
from app.services.order_notifications import DeliveryOutcome


async def test_status_endpoint_commits_new_notification_id_without_write_access_change(
    db_session,
    monkeypatch,
) -> None:
    """Новый Telegram message id сохраняется даже при неизменном write-access."""
    customer = User(telegram_id=830001, telegram_write_access=True)
    manager = User(telegram_id=830002, role=int(UserRole.MANAGER))
    db_session.add_all([customer, manager])
    await db_session.flush()
    order = Order(
        UserId=customer.id,
        user=customer,
        country=Country.THAILAND,
        currencySell="RUB",
        amountSell=10_000,
        currencyBuy="THB",
        amountBuy=3_500,
        status=int(OrderStatus.PROCESSING),
        methodGet="cash",
        publicNumber="MC830001",
        userNotificationMessageId=None,
    )
    db_session.add(order)
    await db_session.commit()

    async def fake_update_order_status(*_args, **_kwargs):
        return order

    async def fake_notify_order_status_changed(target_order, **_kwargs):
        target_order.userNotificationMessageId = 987
        return DeliveryOutcome.SENT

    async def fake_publish(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        "app.api.routers.manager.update_order_status",
        fake_update_order_status,
    )
    monkeypatch.setattr(
        "app.api.routers.manager.notify_order_status_changed",
        fake_notify_order_status_changed,
    )
    monkeypatch.setattr("app.api.routers.manager.manager_realtime_hub.publish", fake_publish)

    await update_manager_order_status(
        order_id=order.id,
        body=ManagerOrderStatusRequest(status=int(OrderStatus.PROCESSING)),
        db=db_session,
        manager=manager,
    )

    await db_session.rollback()
    await db_session.refresh(order)
    assert order.userNotificationMessageId == 987
