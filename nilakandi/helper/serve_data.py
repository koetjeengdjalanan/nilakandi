import pandas as pd

from nilakandi.models import Subscription as SubscriptionsModel


class SubsData:
    def __init__(self, sub: SubscriptionsModel):
        self.sub = sub
        self.services = pd.DataFrame(list(self.sub.services_set.all().values()))
        self.marketplaces = pd.DataFrame(list(self.sub.marketplace_set.all().values()))

    def pivot(self) -> pd.DataFrame:
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
