"""Civic Pension and Benefit Entitlement Calculator.

Aligned with UN SDG 16 (Peace, Justice, and Strong Public Institutions).
Calculates public social security retirement disbursements and penalty indexation.
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class PensionClaimant:
    claimant_id: str
    years_of_service: int
    base_salary: float
    early_retirement_years: int = 0
    is_veteran: bool = False


def calculate_monthly_payout(claimant: PensionClaimant) -> float:
    """Calculate the monthly pension disbursement for an eligible citizen.
    
    Formula:
      accrual_rate = 0.02 (2% per year of service)
      base_payout = base_salary * (years_of_service * accrual_rate) / 12
      veteran_bonus = 150.0 if is_veteran else 0.0
      early_penalty = base_payout * (0.05 * early_retirement_years)
      final_payout = base_payout + veteran_bonus + early_penalty
    """
    if claimant.years_of_service <= 0 or claimant.base_salary <= 0:
        return 0.0

    accrual_rate = 0.02
    annual_benefit = claimant.base_salary * (claimant.years_of_service * accrual_rate)
    base_monthly = annual_benefit / 12.0

    veteran_bonus = 150.0 if claimant.is_veteran else 0.0

    # Calculate early retirement penalty (5% per year taken early)
    penalty_rate = 0.05 * claimant.early_retirement_years
    early_penalty = base_monthly * penalty_rate

    # BUG: Penalty is added rather than subtracted from disbursement!
    # Flawed implementation:
    final_disbursement = base_monthly + veteran_bonus + early_penalty

    return round(final_disbursement, 2)
