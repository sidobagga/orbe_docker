# Default LBO assumptions and parameters
# All monetary values in millions, percentages as percentage points

# LBO Analysis Defaults and Configuration

# Base assumptions for LBO modeling
LBO_ASSUMPTIONS = {
    "base_year": 2025,
    "entry_multiple": 8.6,  # Entry EBITDA multiple
    "exit_multiple": 12.0,  # Exit EBITDA multiple
    "sponsor_target_irr": 25.0,  # Target IRR percentage
    "transaction_fees_pct": 1.5,  # Transaction fees as % of enterprise value (not just equity)
    "cash_to_balance_sheet": 500.0,  # Cash retained on balance sheet (millions)
    "tax_rate_pct": 27.0,  # Corporate tax rate
}

# Debt structure - traditional LBO multiples for small/mid-cap deals
DEBT_STRUCTURE = {
    "first_lien": {
        "multiple_of_ebitda": 4.0,  # Reset to reasonable 4.0x EBITDA
        "interest_rate": 6.5,  # Interest rate percentage
        "term_years": 7,
        "amortization_pct": 1.0,  # Annual amortization as % of original balance
    },
    "second_lien": {
        "multiple_of_ebitda": 1.5,  # Reset to 1.5x EBITDA
        "interest_rate": 9.5,  # Interest rate percentage
        "term_years": 8,
        "amortization_pct": 0.0,  # PIK/bullet payment
    },
    "revolver": {
        "multiple_of_ebitda": 0.5,  # Reset to 0.5x EBITDA
        "interest_rate": 5.5,  # Interest rate percentage
        "commitment_fee": 0.375,  # Commitment fee on unused portion
        "utilization_pct": 0.0,  # Assume undrawn at closing
    },
    "mezzanine": {
        "multiple_of_ebitda": 1.0,  # Reset to 1.0x EBITDA
        "interest_rate": 12.0,  # Cash interest rate
        "pik_rate": 3.0,  # PIK interest rate
        "term_years": 8,
    }
}

# Total debt capacity = 7.0x EBITDA (4.0 + 1.5 + 0.5 + 1.0)
# This is more traditional and reasonable for most LBO targets

# Operating assumptions for projections
OPERATING_ASSUMPTIONS = {
    "sales_growth_rates": [4.5, 4.5, 4.5, 4.5, 4.5],  # Years 1-5 growth rates
    "ebitda_margin_pct": 28.5,  # EBITDA margin percentage
    "ebit_margin_pct": 25.5,   # EBIT margin percentage  
    "d_and_a_pct_of_sales": 3.0,  # D&A as % of sales
    "capex_pct_of_sales": 0.5,    # Capex as % of sales
    "nwc_pct_of_sales": 0.5,      # Net working capital as % of sales
}

# Transaction structure assumptions
TRANSACTION_ASSUMPTIONS = {
    "offer_premium_pct": 15.0,     # Premium to current stock price
    "sponsor_ownership_pct": 95.0,  # Sponsor ownership percentage post-transaction
    "management_rollover_pct": 5.0, # Management rollover percentage
}

# Sensitivity analysis parameters
SENSITIVITY_PARAMS = {
    "entry_multiples": [7.5, 8.0, 8.5, 9.0, 9.5],  # Entry multiple sensitivity
    "exit_multiples": [10.0, 11.0, 12.0, 13.0, 14.0],   # Exit multiple sensitivity
    "sponsor_required_irrs": [15.0, 20.0, 25.0, 30.0, 35.0],  # Sponsor required IRR % for sensitivity
}

# Financial metrics thresholds for validation
VALIDATION_THRESHOLDS = {
    "min_dscr": 1.25,              # Minimum debt service coverage ratio
    "max_total_leverage": 8.5,      # Maximum total debt / EBITDA
    "max_first_lien_leverage": 4.5, # Maximum first lien / EBITDA
    "min_equity_contribution": 15.0, # Minimum equity as % of sources
    "max_cash_buffer": 10000.0,     # Maximum negative net debt (cash position) in millions
    "min_share_price": 0.01,        # Minimum share price in dollars
    "min_shares_outstanding": 0.01,  # Minimum shares outstanding in millions
    "min_sales": 0.01,              # Minimum sales in millions
    "min_enterprise_value": 1.0,    # Minimum enterprise value in millions
    "min_equity_offer_price": 1.0,  # Minimum equity offer price in millions
    "min_sponsor_equity": 1.0,      # Minimum sponsor equity in millions
    "max_entry_multiple": 50.0,     # Maximum entry multiple
    "min_entry_multiple": 5.0,      # Minimum entry multiple
    "max_exit_multiple": 50.0,      # Maximum exit multiple
    "min_exit_multiple": 5.0,       # Minimum exit multiple
    "max_irr": 1000.0,              # Maximum IRR percentage
    "min_irr": -100.0,              # Minimum IRR percentage
}

# Magic numbers exposed as configurable parameters
CALCULATION_CONSTANTS = {
    "revenue_multiple_for_negative_ebitda": 1.5,  # Revenue multiple for loss-making companies
    "blended_interest_rate": 7.0,                 # Blended debt interest rate percentage
    "min_sponsor_equity_pct": 10.0,              # Minimum sponsor equity as % of total uses
    "hold_period_years": 5,                       # LBO hold period in years
    "ebitda_growth_for_negative_companies": 15.0, # EBITDA growth % for loss-making companies
    "min_ebitda_target_margin": 5.0,             # Minimum EBITDA margin target for loss-making companies
    "min_ebitda_target_absolute": 50.0,          # Minimum absolute EBITDA target in millions
}

# Cache settings
CACHE_SETTINGS = {
    "redis_ttl": 120,  # Cache TTL in seconds
    "enable_caching": True,
}

# Database connection settings
DATABASE_CONFIG = {
    "host": "orbe360.ai",
    "port": 5432,
    "database": "finmetrics",
    "username": "postgres",
    "password": "Admin0rbE",
}

# Financial Modeling Prep API settings  
FMP_CONFIG = {
    "base_url": "https://financialmodelingprep.com/api/v3",
    "api_key": "demo",  # Replace with actual API key
    "timeout": 10,
}

def get_debt_amounts(ltm_ebitda: float) -> dict:
    """
    Calculate debt amounts based on LTM EBITDA and debt structure multiples.
    Handles negative EBITDA by using minimal debt structure.
    
    Args:
        ltm_ebitda: LTM EBITDA in millions
        
    Returns:
        Dictionary with debt amounts in millions
    """
    # Handle negative EBITDA case - use minimal debt structure
    if ltm_ebitda <= 0:
        first_lien = 0.0
        second_lien = 0.0
        mezzanine = 0.0
        revolver_capacity = 100.0  # Small revolver for working capital
        revolver_drawn = 0.0
        total_debt = first_lien + second_lien + mezzanine
        
        return {
            "first_lien": first_lien,
            "second_lien": second_lien,
            "mezzanine": mezzanine,
            "revolver_capacity": revolver_capacity,
            "revolver_drawn": revolver_drawn,
            "total_debt": total_debt
        }

    # Calculate debt amounts for profitable companies
    first_lien = ltm_ebitda * DEBT_STRUCTURE["first_lien"]["multiple_of_ebitda"]
    second_lien = ltm_ebitda * DEBT_STRUCTURE["second_lien"]["multiple_of_ebitda"]
    mezzanine = ltm_ebitda * DEBT_STRUCTURE["mezzanine"]["multiple_of_ebitda"]
    revolver_capacity = ltm_ebitda * DEBT_STRUCTURE["revolver"]["multiple_of_ebitda"]
    revolver_drawn = revolver_capacity * DEBT_STRUCTURE["revolver"]["utilization_pct"]
    
    # Calculate total debt consistently
    total_debt = first_lien + second_lien + mezzanine + revolver_drawn
    
    return {
        "first_lien": first_lien,
        "second_lien": second_lien,
        "mezzanine": mezzanine,
        "revolver_capacity": revolver_capacity,
        "revolver_drawn": revolver_drawn,
        "total_debt": total_debt
    }

def get_interest_expense(debt_amounts: dict) -> float:
    """
    Calculate annual cash interest expense based on debt amounts and rates.
    
    Args:
        debt_amounts: Dictionary with debt amounts
        
    Returns:
        Annual cash interest expense in millions
    """
    interest_expense = 0.0
    
    # First lien interest
    interest_expense += debt_amounts["first_lien"] * (DEBT_STRUCTURE["first_lien"]["interest_rate"] / 100)
    
    # Second lien interest  
    interest_expense += debt_amounts["second_lien"] * (DEBT_STRUCTURE["second_lien"]["interest_rate"] / 100)
    
    # Revolver interest (on drawn amount)
    interest_expense += debt_amounts["revolver_drawn"] * (DEBT_STRUCTURE["revolver"]["interest_rate"] / 100)
    
    # Mezzanine cash interest
    interest_expense += debt_amounts["mezzanine"] * (DEBT_STRUCTURE["mezzanine"]["interest_rate"] / 100)
    
    return interest_expense

# Debt structure defaults
DEBT_DEFAULTS = {
    "firstLien": {
        "term": 7,  # years
        "spread": 3.5,  # percentage points over SOFR
        "mandatoryAmortPct": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],  # by year
        "description": "First Lien Term Loan"
    },
    "secondLien": {
        "term": 8,  # years
        "spread": 7.0,  # percentage points over SOFR
        "mandatoryAmortPct": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # bullet
        "description": "Second Lien"
    }
}

# Financial projection defaults
PROJECTION_DEFAULTS = {
    "projectionYears": 6,  # Base year + 5 projection years
    "salesGrowthRates": [4.5, 4.5, 4.5, 4.5, 4.5],  # Years 1-5
    "ebitdaMargins": [28.5, 30.6, 30.6, 30.6, 30.6],  # Years 1-5
    "dAndAMargins": [3.0, 4.0, 4.0, 4.0, 4.0],  # Years 1-5
    "capexMargins": [0.5, 0.5, 0.5, 0.5, 0.5],  # Years 1-5
    "nwcMargins": [0.5, 0.5, 0.5, 0.5, 0.5],  # Years 1-5
}

# Market data defaults (fallbacks if not available)
MARKET_DEFAULTS = {
    "currentSharePrice": 25.23,
    "basicShares": 62.6,
    "fullyDilutedShares": 63.2,
    "marketCap": 1580.0,  # millions
}

def get_default_value(parameter_name: str, default_value=None):
    """Get default value for a parameter with fallback."""
    return LBO_ASSUMPTIONS.get(parameter_name, default_value)

def get_debt_defaults(tranche_type: str):
    """Get debt defaults for a specific tranche type."""
    return DEBT_DEFAULTS.get(tranche_type, {})

def get_projection_defaults():
    """Get financial projection defaults."""
    return PROJECTION_DEFAULTS.copy()

def get_market_defaults():
    """Get market data defaults."""
    return MARKET_DEFAULTS.copy()

# Validation ranges for parameters
PARAMETER_RANGES = {
    "entryMultiple": (5.0, 20.0),
    "exitMultiple": (8.0, 30.0),
    "sponsorTargetIRR": (15.0, 50.0),
    "transactionFeesPct": (1.0, 10.0),
    "taxRatePct": (15.0, 40.0),
    "offerPremiumPct": (0.0, 50.0),
    "salesGrowthPct": (-10.0, 25.0),
    "ebitdaMarginPct": (5.0, 50.0),
    "capexAsPctOfSales": (0.1, 10.0),
    "nwcAsPctOfSales": (-5.0, 15.0),
}

def validate_parameter(parameter_name: str, value: float) -> bool:
    """Validate parameter value against acceptable ranges."""
    if parameter_name not in PARAMETER_RANGES:
        return True  # No validation range defined
    
    min_val, max_val = PARAMETER_RANGES[parameter_name]
    return min_val <= value <= max_val

def get_parameter_range(parameter_name: str):
    """Get acceptable range for a parameter."""
    return PARAMETER_RANGES.get(parameter_name, (None, None)) 