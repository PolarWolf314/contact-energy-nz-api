"""Pydantic models for API requests and responses."""

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    timestamp: datetime = Field(default_factory=datetime.now)


class UsageData(BaseModel):
    """Individual usage data point."""

    date: datetime
    value: float = Field(description="Usage value in kWh or gas units")
    unit: str = Field(description="Unit of measurement (kWh, units, etc.)")
    dollar_value: float | None = Field(default=None, description="Cost in NZD")
    offpeak_value: float | None = Field(default=None, description="Off-peak usage")
    offpeak_dollar_value: float | None = Field(
        default=None, description="Off-peak cost in NZD"
    )
    uncharged_value: float | None = Field(
        default=None, description="Uncharged usage value"
    )


class HourlyUsageData(BaseModel):
    """Hourly usage data for a specific day."""

    date: datetime = Field(description="The date for which hourly data is returned")
    hours: list[UsageData] = Field(description="Hourly usage breakdown")
    total_value: float = Field(description="Total usage for the day")
    total_dollar_value: float | None = Field(
        default=None, description="Total cost for the day"
    )


class MonthlyAggregate(BaseModel):
    """Aggregated monthly usage data."""

    month: str = Field(description="Month in YYYY-MM format")
    value: float = Field(description="Total usage for the month")
    unit: str = Field(description="Unit of measurement")
    dollar_value: float | None = Field(default=None, description="Total cost in NZD")
    daily_average: float = Field(description="Average daily usage")
    days_with_data: int = Field(description="Number of days with data")


class Comparisons(BaseModel):
    """Usage comparison percentages."""

    vs_yesterday: float | None = Field(
        default=None, description="Percentage change vs yesterday"
    )
    vs_last_month: float | None = Field(
        default=None, description="Percentage change vs last month"
    )
    vs_same_day_last_week: float | None = Field(
        default=None, description="Percentage change vs same day last week"
    )


class UsageSummary(BaseModel):
    """Complete usage summary with comparisons."""

    contract_id: str
    today: UsageData | None = Field(default=None, description="Today's usage so far")
    yesterday: UsageData | None = Field(default=None, description="Yesterday's total")
    this_month: MonthlyAggregate | None = Field(
        default=None, description="Current month aggregate"
    )
    last_month: MonthlyAggregate | None = Field(
        default=None, description="Previous month aggregate"
    )
    comparisons: Comparisons = Field(
        default_factory=Comparisons, description="Usage comparisons"
    )


class Contract(BaseModel):
    """A Contact Energy contract."""

    contract_id: str
    account_id: str


class Account(BaseModel):
    """A Contact Energy account with its contracts."""

    account_id: str
    contracts: list[Contract] = Field(default_factory=list)


class AccountsResponse(BaseModel):
    """Response for the accounts endpoint."""

    accounts: list[Account] = Field(default_factory=list)


class CurrentUsageResponse(BaseModel):
    """Response for current usage endpoint."""

    contract_id: str
    current_month: MonthlyAggregate | None = None
    today: UsageData | None = None


class MonthlyUsageResponse(BaseModel):
    """Response for monthly usage range endpoint."""

    contract_id: str
    start_month: str
    end_month: str
    months: list[MonthlyAggregate] = Field(default_factory=list)
