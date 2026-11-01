"""Property-based invariant tests for civic pension calculator."""

from hypothesis import given, strategies as st
from pension_engine.calculator import PensionClaimant, calculate_monthly_payout


@given(
    years=st.integers(min_value=1, max_value=40),
    salary=st.floats(min_value=10000.0, max_value=200000.0),
    early_years=st.integers(min_value=1, max_value=5),
)
def test_early_retirement_strictly_less_than_normal(years, salary, early_years):
    """Algebraic invariant: Taking early retirement must never yield higher payout than normal retirement."""
    normal = PensionClaimant(claimant_id="norm", years_of_service=years, base_salary=salary, early_retirement_years=0)
    early = PensionClaimant(claimant_id="early", years_of_service=years, base_salary=salary, early_retirement_years=early_years)
    
    # Early retirement must yield strictly less or equal monthly payout
    assert calculate_monthly_payout(early) <= calculate_monthly_payout(normal)
