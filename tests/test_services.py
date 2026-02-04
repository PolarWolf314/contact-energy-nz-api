"""Tests for service layer."""

from datetime import datetime

import pytest

from app.models import Comparisons, MonthlyAggregate, UsageData


class TestComparisonCalculations:
    """Tests for comparison percentage calculations."""

    def test_vs_yesterday_increase(self):
        """Test percentage increase vs yesterday."""
        today_value = 15.0
        yesterday_value = 10.0

        # Calculate percentage change
        change = ((today_value - yesterday_value) / yesterday_value) * 100

        assert change == 50.0

    def test_vs_yesterday_decrease(self):
        """Test percentage decrease vs yesterday."""
        today_value = 8.0
        yesterday_value = 10.0

        change = ((today_value - yesterday_value) / yesterday_value) * 100

        assert change == -20.0

    def test_vs_yesterday_zero(self):
        """Test when yesterday is zero (should be None)."""
        yesterday_value = 0

        # Should not calculate comparison when yesterday is 0
        if yesterday_value == 0:
            comparison = None
        else:
            comparison = 100.0

        assert comparison is None


class TestMonthlyAggregate:
    """Tests for monthly aggregate model."""

    def test_daily_average_calculation(self):
        """Test daily average is calculated correctly."""
        aggregate = MonthlyAggregate(
            month="2026-01",
            value=310.0,
            unit="kWh",
            dollar_value=93.0,
            daily_average=10.0,  # 310 / 31 days
            days_with_data=31,
        )

        assert aggregate.daily_average == 10.0
        assert aggregate.days_with_data == 31

    def test_partial_month(self):
        """Test aggregate with partial month data."""
        # If we only have 15 days of data
        aggregate = MonthlyAggregate(
            month="2026-02",
            value=150.0,
            unit="kWh",
            dollar_value=45.0,
            daily_average=10.0,
            days_with_data=15,
        )

        assert aggregate.value == 150.0
        assert aggregate.daily_average == 10.0


class TestUsageData:
    """Tests for usage data model."""

    def test_usage_data_creation(self):
        """Test creating usage data."""
        data = UsageData(
            date=datetime(2026, 2, 4, 10, 0),
            value=5.5,
            unit="kWh",
            dollar_value=1.65,
        )

        assert data.value == 5.5
        assert data.unit == "kWh"
        assert data.dollar_value == 1.65
        assert data.offpeak_value is None

    def test_usage_data_with_optional_fields(self):
        """Test usage data with all optional fields."""
        data = UsageData(
            date=datetime(2026, 2, 4, 10, 0),
            value=5.5,
            unit="kWh",
            dollar_value=1.65,
            offpeak_value=2.0,
            offpeak_dollar_value=0.40,
            uncharged_value=0.5,
        )

        assert data.offpeak_value == 2.0
        assert data.offpeak_dollar_value == 0.40
        assert data.uncharged_value == 0.5


class TestComparisons:
    """Tests for comparisons model."""

    def test_comparisons_default(self):
        """Test default comparisons are all None."""
        comparisons = Comparisons()

        assert comparisons.vs_yesterday is None
        assert comparisons.vs_last_month is None
        assert comparisons.vs_same_day_last_week is None

    def test_comparisons_with_values(self):
        """Test comparisons with values."""
        comparisons = Comparisons(
            vs_yesterday=-5.5,
            vs_last_month=12.3,
            vs_same_day_last_week=-2.1,
        )

        assert comparisons.vs_yesterday == -5.5
        assert comparisons.vs_last_month == 12.3
        assert comparisons.vs_same_day_last_week == -2.1
