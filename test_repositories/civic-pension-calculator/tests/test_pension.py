import pytest
from pension_engine.calculator import PensionClaimant, calculate_monthly_payout


def test_standard_retirement_payout():
    # 25 years of service, $60,000 base salary -> 50% = $30,000/yr -> $2,500/mo
    c = PensionClaimant(claimant_id="C001", years_of_service=25, base_salary=60000.0)
    assert calculate_monthly_payout(c) == 2500.0


def test_veteran_bonus_payout():
    # 20 years, $48,000 base -> 40% = $19,200/yr -> $1,600/mo + $150 = $1,750
    c = PensionClaimant(claimant_id="C002", years_of_service=20, base_salary=48000.0, is_veteran=True)
    assert calculate_monthly_payout(c) == 1750.0


def test_zero_years_service():
    c = PensionClaimant(claimant_id="C003", years_of_service=0, base_salary=50000.0)
    assert calculate_monthly_payout(c) == 0.0


def test_early_retirement_penalty_applied():
    # 30 years, $72,000 base -> $3,600/mo
    # 2 years early retirement -> 10% penalty ($360) -> Expected: $3,600 - $360 = $3,240.0
    # Due to bug (added instead of subtracted), returns $3,960.0
    c = PensionClaimant(claimant_id="C004", years_of_service=30, base_salary=72000.0, early_retirement_years=2)
    assert calculate_monthly_payout(c) == 3240.0


def test_veteran_with_early_penalty():
    # 25 years, $60,000 base -> $2,500 + $150 bonus = $2,650
    # 1 year early -> 5% of $2,500 = $125 penalty -> Expected: $2,650 - $125 = $2,525.0
    c = PensionClaimant(claimant_id="C005", years_of_service=25, base_salary=60000.0, early_retirement_years=1, is_veteran=True)
    assert calculate_monthly_payout(c) == 2525.0
