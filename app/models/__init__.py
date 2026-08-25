"""Экспорт всех моделей."""

from app.models.admin import Admin
from app.models.aex import AexLedgerEntry, AexPartnerRate, AexPersonalRate, AexRate, AexWallet
from app.models.attribution import (
    AttributionAuditEvent,
    MarketingTouch,
    OrderAttribution,
    UserAcquisition,
)
from app.models.chat import ChatAttachment, ChatConversation, ChatMessage, ChatMessageRevision
from app.models.city import City
from app.models.config import Config
from app.models.marketing import (
    MarketingAttribution,
    MarketingCampaign,
    MarketingCurrency,
    MarketingDailyMetric,
    MarketingPlatform,
)
from app.models.order import Order
from app.models.order_number_counter import OrderNumberCounter
from app.models.rate import Rate
from app.models.site_lead import SiteLead
from app.models.user import User
from app.modules.broadcasts.models import Broadcast

__all__ = [
    "Admin",
    "AexLedgerEntry",
    "AexPartnerRate",
    "AexPersonalRate",
    "AexRate",
    "AexWallet",
    "AttributionAuditEvent",
    "Broadcast",
    "ChatAttachment",
    "ChatConversation",
    "ChatMessage",
    "ChatMessageRevision",
    "City",
    "Config",
    "MarketingAttribution",
    "MarketingCampaign",
    "MarketingCurrency",
    "MarketingDailyMetric",
    "MarketingPlatform",
    "MarketingTouch",
    "Order",
    "OrderAttribution",
    "OrderNumberCounter",
    "Rate",
    "SiteLead",
    "User",
    "UserAcquisition",
]
