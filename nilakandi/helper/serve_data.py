import pandas as pd

from nilakandi.models import Subscription as SubscriptionsModel


class SubsData:
    def __init__(self, sub: SubscriptionsModel, total_month: bool = True):
        self.sub = sub
        self.total_month = total_month
        self.services = pd.DataFrame(list(self.sub.services_set.all().values()))
        self.marketplaces = pd.DataFrame(list(self.sub.marketplace_set.all().values()))

    def service(self) -> pd.DataFrame:
        if self.services.empty:
            return pd.DataFrame()
        self.services["usage_date"] = (
            pd.to_datetime(self.services["usage_date"])
            .dt.to_period("M")
            .dt.strftime("%B %Y")
            if self.total_month
            else self.services["usage_date"]
        )
        table = pd.pivot_table(
            self.services,
            values="cost_usd",
            index=["service_name", "service_tier", "meter"],
            columns=["usage_date"],
            aggfunc="sum",
            margins=True,
            margins_name="Grand Total",
        )
        return table

    def marketplace(self) -> pd.DataFrame:
        if self.marketplaces.empty:
            return pd.DataFrame()
        self.marketplaces["usage_start"] = (
            pd.to_datetime(self.marketplaces["usage_start"])
            .dt.to_period("M")
            .dt.strftime("%B %Y")
            if self.total_month
            else self.marketplaces["usage_start"]
        )
        table = pd.pivot_table(
            self.marketplaces,
            values="pretax_cost",
            index=["subscription_name", "publisher_name", "plan_name"],
            columns=["usage_start"],
            aggfunc="sum",
            margins=True,
            margins_name="Grand Total",
        )
        return table
