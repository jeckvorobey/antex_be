from __future__ import annotations

from app.models import MarketingAttribution, MarketingCampaign, MarketingDailyMetric
from app.models.base import Base


def test_marketing_metadata_has_tables_constraints_and_indexes() -> None:
    campaign = MarketingCampaign.__table__
    attribution = MarketingAttribution.__table__
    daily = MarketingDailyMetric.__table__

    assert campaign.name == "MarketingCampaigns"
    assert attribution.name == "MarketingAttributions"
    assert daily.name == "MarketingDailyMetrics"
    assert campaign.c.code.unique is True
    assert attribution.c.user_id.unique is True
    assert {foreign_key.target_fullname for foreign_key in attribution.foreign_keys} == {
        "MarketingCampaigns.id",
        "Users.id",
    }
    assert any(
        set(constraint.columns.keys()) == {"campaign_id", "metric_date"}
        for constraint in daily.constraints
    )
    assert {index.name for index in campaign.indexes} >= {
        "ix_marketing_campaigns_provider_status",
    }
    assert {index.name for index in attribution.indexes} >= {
        "ix_marketing_attributions_campaign_attributed",
    }


def test_marketing_models_do_not_add_columns_to_users_or_orders() -> None:
    marketing_columns = {"campaign_id", "marketing_campaign_id", "marketing_code"}

    for table_name in ("Users", "Orders"):
        table = Base.metadata.tables[table_name]
        assert marketing_columns.isdisjoint(table.columns.keys())
        assert all(
            foreign_key.target_fullname != "MarketingCampaigns.id"
            for foreign_key in table.foreign_keys
        )
