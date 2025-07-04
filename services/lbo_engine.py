"""
LBO Engine - Core financial modeling calculations for Leveraged Buyout analysis.

This module implements the complete LBO model including:
- Purchase price calculation
- Sources & uses of funds
- Debt structure and amortization
- Financial projections
- Returns analysis and IRR calculation
- Sensitivity analysis
- Support for both public and private companies
"""

import logging
import math
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from defaults import (
    LBO_ASSUMPTIONS, DEBT_STRUCTURE, OPERATING_ASSUMPTIONS, 
    TRANSACTION_ASSUMPTIONS, SENSITIVITY_PARAMS, VALIDATION_THRESHOLDS, CALCULATION_CONSTANTS,
    get_debt_amounts, get_interest_expense
)
from .financial_data_service import get_comprehensive_financial_data

logger = logging.getLogger(__name__)

# Private company defaults
DEFAULTS_PRIVATE = {
    "ltm_ebitda": 50.0,  # $50M default EBITDA
    "ltm_sales": 150.0,  # $150M default sales
    "net_debt": 0.0,     # No debt assumption
    "entry_multiple": 8.0,
    "exit_multiple": 10.0,
    "cash_to_balance_sheet": 5.0,
    "transaction_fees_pct": 5.0,
    "tax_rate_pct": 27.0
}

def validate_financial_data(financial_data: Dict[str, Any], is_private: bool = False) -> Tuple[Dict[str, Any], List[str]]:
    """
    Validate and sanitize financial data to prevent negative values and calculation errors.
    
    Args:
        financial_data: Raw financial data dictionary
        is_private: Whether this is a private company deal
        
    Returns:
        Tuple of (validated financial data dictionary, list of fields that were defaulted)
    """
    validated_data = financial_data.copy()
    defaults_applied = []
    
    if is_private:
        # Private company validation - focus on core metrics
        required_fields = ["ltm_ebitda", "ltm_sales", "net_debt"]
        
        for field in required_fields:
            current_value = validated_data.get(field)
            if current_value is None or (isinstance(current_value, (int, float)) and current_value == 0 and field != "net_debt"):
                default_value = DEFAULTS_PRIVATE[field]
                validated_data[field] = default_value
                defaults_applied.append(field)
                logger.warning(f"PRIVATE COMPANY - substituted default {field} = {default_value}")
        
        # Ensure minimum positive values for ltm_ebitda and ltm_sales
        if validated_data["ltm_ebitda"] <= 0:
            validated_data["ltm_ebitda"] = DEFAULTS_PRIVATE["ltm_ebitda"]
            if "ltm_ebitda" not in defaults_applied:
                defaults_applied.append("ltm_ebitda")
            logger.warning(f"PRIVATE COMPANY - negative EBITDA replaced with default {DEFAULTS_PRIVATE['ltm_ebitda']}")
        
        if validated_data["ltm_sales"] <= 0:
            validated_data["ltm_sales"] = DEFAULTS_PRIVATE["ltm_sales"]
            if "ltm_sales" not in defaults_applied:
                defaults_applied.append("ltm_sales")
            logger.warning(f"PRIVATE COMPANY - negative sales replaced with default {DEFAULTS_PRIVATE['ltm_sales']}")
        
        # Net debt can be negative (net cash), so just ensure it's a number
        validated_data["net_debt"] = float(validated_data.get("net_debt", 0))
        
    else:
        # Public company validation (existing logic)
        min_shares = VALIDATION_THRESHOLDS.get("min_shares_outstanding", 0.01)
        min_price = VALIDATION_THRESHOLDS.get("min_share_price", 0.01)
        min_sales = VALIDATION_THRESHOLDS.get("min_sales", 0.01)
        max_cash_buffer = VALIDATION_THRESHOLDS.get("max_cash_buffer", 10000.0)
        
        # Ensure critical fields are positive or have reasonable minimums
        validated_data["basic_shares"] = max(min_shares, validated_data.get("basic_shares", 1.0))
        validated_data["fully_diluted_shares"] = max(min_shares, validated_data.get("fully_diluted_shares", 1.0))
        validated_data["current_share_price"] = max(min_price, validated_data.get("current_share_price", 1.0))
        validated_data["ltm_sales"] = max(min_sales, validated_data.get("ltm_sales", 1.0))
        
        # Clamp and sanitize net_debt up-front
        validated_data["net_debt"] = float(validated_data.get("net_debt", 0))
        # Prevent absurdly negative net cash (negative net debt)
        validated_data["net_debt"] = max(-max_cash_buffer, validated_data["net_debt"])
        
        # EBITDA can be negative, but we'll handle that in calculations
        validated_data["ltm_ebitda"] = float(validated_data.get("ltm_ebitda", 0))
        
        # Log any adjustments made
        adjustments = []
        for key in ["basic_shares", "fully_diluted_shares", "current_share_price", "ltm_sales", "net_debt"]:
            original_val = financial_data.get(key, 0)
            new_val = validated_data[key]
            if abs(new_val - original_val) > 0.001:  # Account for floating point precision
                adjustments.append(f"{key}: {original_val or 0:.3f} → {new_val:.3f}")
        
        if adjustments:
            logger.info(f"Financial data adjustments made: {'; '.join(adjustments)}")
    
    return validated_data, defaults_applied

async def run_lbo(ticker: str, overrides: Dict[str, Any], session: AsyncSession, is_private: bool = False) -> Dict[str, Any]:
    """
    Run complete LBO analysis for a given ticker with optional overrides.
    
    Args:
        ticker: Company ticker symbol or identifier
        overrides: Dictionary of override values for assumptions
        session: Async database session
        is_private: Whether this is a private company deal
        
    Returns:
        Complete LBO analysis results matching the JSON contract
    """
    try:
        # Step 1: Get base financial data
        if is_private:
            # For private companies, expect data from overrides or use defaults
            financial_data = {
                "ltm_ebitda": overrides.get("ltm_ebitda"),
                "ltm_sales": overrides.get("ltm_sales"), 
                "net_debt": overrides.get("net_debt")
            }
        else:
            financial_data = await get_financial_data(ticker, session)
        
        # Step 1.5: Validate and sanitize financial data
        financial_data, defaults_applied = validate_financial_data(financial_data, is_private)
        
        # Step 1.5: Validate that company is suitable for LBO analysis
        ltm_ebitda = financial_data.get("ltm_ebitda", 0)
        if ltm_ebitda <= 0:
            # Allow override for testing/analysis purposes
            allow_negative_ebitda = overrides.get("allow_negative_ebitda", False)
            if not allow_negative_ebitda:
                logger.warning(f"LBO analysis attempted on unprofitable company {ticker} with EBITDA: ${ltm_ebitda:.1f}M")
                # Return a structured response indicating why LBO is not suitable
                return {
                    "error": "UNSUITABLE_FOR_LBO",
                    "message": f"LBO analysis not applicable for {ticker}: Company has negative LTM EBITDA of ${ltm_ebitda:.1f}M",
                    "explanation": "LBO models require profitable companies with positive cash flow to support debt financing. Consider operational improvements or distressed acquisition strategies instead.",
                    "ticker": ticker,
                    "ltm_ebitda": ltm_ebitda,
                    "ltm_sales": financial_data.get("ltm_sales", 0),
                    "recommendation": "This company may be better suited for a turnaround investment or distressed acquisition analysis rather than a traditional LBO."
                }
        
        # Step 2: Create working assumptions with company-specific defaults
        working_assumptions = LBO_ASSUMPTIONS.copy()
        
        # For private companies, use private-specific defaults
        if is_private:
            working_assumptions.update({
                "entry_multiple": DEFAULTS_PRIVATE["entry_multiple"],
                "exit_multiple": DEFAULTS_PRIVATE["exit_multiple"], 
                "cash_to_balance_sheet": DEFAULTS_PRIVATE["cash_to_balance_sheet"],
                "transaction_fees_pct": DEFAULTS_PRIVATE["transaction_fees_pct"],
                "tax_rate_pct": DEFAULTS_PRIVATE["tax_rate_pct"]
            })
        elif "current_enterprise_multiple" in financial_data and financial_data["current_enterprise_multiple"]:
            company_params = generate_company_specific_sensitivity_params(financial_data["current_enterprise_multiple"])
            
            # Set company-specific defaults if not overridden by user
            if "entry_multiple" not in overrides and "entryMultiple" not in overrides:
                # Check nested overrides too
                has_entry_override = ("assumptions" in overrides and 
                                    ("entryMultiple" in overrides["assumptions"] or 
                                     "entry_multiple" in overrides["assumptions"]))
                if not has_entry_override:
                    working_assumptions["entry_multiple"] = company_params["entry_multiple"]
                    logger.info(f"Using company-specific entry multiple: {company_params['entry_multiple'] or 0:.1f}x")
            
            if "exit_multiple" not in overrides and "exitMultiple" not in overrides:
                # Check nested overrides too
                has_exit_override = ("assumptions" in overrides and 
                                   ("exitMultiple" in overrides["assumptions"] or 
                                    "exit_multiple" in overrides["assumptions"]))
                if not has_exit_override:
                    # Use the middle exit multiple (same as entry) as default
                    working_assumptions["exit_multiple"] = company_params["exit_multiples"][1]
                    logger.info(f"Using company-specific exit multiple: {company_params['exit_multiples'][1] or 0:.1f}x")
        
        # Step 3: Extract separate override sections
        assumptions_overrides = overrides.get("assumptions", {})
        purchase_price_overrides = overrides.get("purchasePrice", {})
        financial_projections_overrides = overrides.get("financialProjections", [])
        
        # Add top-level assumption overrides to assumptions_overrides
        for key in ["baseYear", "entryMultiple", "exitMultiple", "sponsorTargetIRR", 
                   "transactionFeesPct", "cashToBalanceSheet", "taxRatePct", "allowNegativeEbitda"]:
            if key in overrides:
                assumptions_overrides[key] = overrides[key]
        
        # Private company financial data overrides
        if is_private:
            for key in ["ltm_ebitda", "ltm_sales", "net_debt"]:
                if key in overrides:
                    financial_data[key] = overrides[key]
                    logger.info(f"Override applied: {key} = {overrides[key]}")
        
        # Step 4: Merge working assumptions with user overrides
        assumptions = merge_assumptions(working_assumptions, assumptions_overrides, is_private)
        
        # Step 5: Apply purchase price overrides to financial data
        if purchase_price_overrides:
            apply_purchase_price_overrides(financial_data, purchase_price_overrides)
        
        # Step 6: Calculate purchase price
        if is_private:
            purchase_price = calculate_purchase_price_private(financial_data, assumptions)
        else:
            purchase_price = calculate_purchase_price(financial_data, assumptions)
        
        # Step 7: Calculate debt amounts based on EBITDA
        debt_amounts = get_debt_amounts(financial_data["ltm_ebitda"])
        
        # Step 8: Calculate sources and uses
        sources_uses = calculate_sources_and_uses(purchase_price, assumptions, debt_amounts, financial_data, is_private)
        
        # Step 9: Build pro forma cap table
        cap_table = build_pro_forma_cap_table(sources_uses, financial_data, assumptions, debt_amounts, is_private)
        
        # Step 10: Generate financial projections (with overrides)
        projections = generate_financial_projections(financial_data, assumptions, debt_amounts, financial_projections_overrides)
        
        # Step 11: Calculate returns analysis
        returns = calculate_returns_analysis(projections, cap_table, assumptions, debt_amounts, is_private)
        
        # Step 12: Generate IRR sensitivity
        irr_sensitivity = await generate_irr_sensitivity(financial_data, assumptions, ticker, session, is_private)
        
        # Step 13: Assemble final response
        response = {
            "purchasePrice": purchase_price,
            "assumptions": {
                "baseYear": assumptions["base_year"],
                "entryMultiple": assumptions["entry_multiple"],
                "exitMultiple": assumptions["exit_multiple"],
                "sponsorTargetIRR": assumptions["sponsor_target_irr"],
                "transactionFeesPct": assumptions["transaction_fees_pct"],
                "cashToBalanceSheet": assumptions["cash_to_balance_sheet"],
                "taxRatePct": assumptions["tax_rate_pct"]
            },
            "sourcesAndUses": sources_uses,
            "proFormaCapTable": cap_table,
            "returnsAnalysis": returns,
            "irrSensitivity": irr_sensitivity,
            "financialProjections": projections
        }
        
        # Add defaults applied tracking for private companies
        if is_private and defaults_applied:
            response["defaultsApplied"] = defaults_applied
            
        return response
        
    except Exception as e:
        logger.error(f"Error in LBO analysis for {ticker}: {e}")
        raise

async def get_financial_data(ticker: str, session: AsyncSession) -> Dict[str, Any]:
    """Get financial data for the ticker from Financial Modeling Prep API."""
    try:
        # First try to get real financial data from FMP API
        financial_data = await get_comprehensive_financial_data(ticker)
        logger.info(f"Successfully fetched real financial data for {ticker}")
        return financial_data
        
    except Exception as e:
        logger.warning(f"Failed to fetch real financial data for {ticker}: {e}")
        
        # Fallback to database if API fails
        try:
            query = text("""
                SELECT 
                    symbol,
                    date,
                    fiscalyear,
                    metric_type,
                    metric_values
                FROM financial_metrics 
                WHERE symbol = :ticker 
                AND metric_type IN ('income', 'balance', 'ratio')
                ORDER BY fiscalyear DESC, date DESC
                LIMIT 20
            """)
            
            result = await session.execute(query, {"ticker": ticker})
            rows = result.fetchall()
            
            if not rows:
                raise ValueError(f"No financial data found for {ticker}")
            
            # Extract key metrics from database
            financial_data = {
                "ltm_ebitda": 261.0,  # Default fallback
                "ltm_sales": 881.0,   # Default fallback
                "current_share_price": 150.0,
                "basic_shares": 16500.0,  # 16.5B shares
                "fully_diluted_shares": 16800.0,  # 16.8B shares
                "net_debt": 80000.0,    # ~$80B net debt for Apple
            }
            
            # Try to extract actual values from database
            for row in rows:
                metric_values = row.metric_values or {}
                
                if row.metric_type == 'income':
                    if 'ebitda' in metric_values:
                        financial_data["ltm_ebitda"] = float(metric_values['ebitda']) / 1_000_000
                    if 'revenue' in metric_values:
                        financial_data["ltm_sales"] = float(metric_values['revenue']) / 1_000_000
                    elif 'totalrevenue' in metric_values:
                        financial_data["ltm_sales"] = float(metric_values['totalrevenue']) / 1_000_000
                        
                elif row.metric_type == 'balance':
                    if 'totaldebt' in metric_values and 'cashandcashequivalents' in metric_values:
                        total_debt = float(metric_values.get('totaldebt', 0)) / 1_000_000
                        cash = float(metric_values.get('cashandcashequivalents', 0)) / 1_000_000
                        financial_data["net_debt"] = max(0, total_debt - cash)
                        
                elif row.metric_type == 'ratio':
                    if 'weightedaverageshsout' in metric_values:
                        financial_data["basic_shares"] = float(metric_values['weightedaverageshsout']) / 1_000_000
                    if 'weightedaverageshsoutdil' in metric_values:
                        financial_data["fully_diluted_shares"] = float(metric_values['weightedaverageshsoutdil']) / 1_000_000
            
            logger.info(f"Using database fallback data for {ticker}")
            return financial_data
            
        except Exception as db_error:
            logger.error(f"Database fallback also failed for {ticker}: {db_error}")
            # Final fallback to mega-cap defaults
            return {
                "ltm_ebitda": 138866.0,  # Apple's actual LTM EBITDA
                "ltm_sales": 400366.0,   # Apple's actual LTM sales
                "current_share_price": 202.82,
                "basic_shares": 14935.8,
                "fully_diluted_shares": 15383.874,
                "net_debt": 80000.0,  # Realistic Apple net debt
            }

def merge_assumptions(defaults: Dict[str, Any], overrides: Dict[str, Any], is_private: bool = False) -> Dict[str, Any]:
    """Merge default assumptions with user overrides with validation."""
    assumptions = defaults.copy()
    
    # Key mapping from camelCase (API) to snake_case (defaults)
    key_mapping = {
        "baseYear": "base_year",
        "entryMultiple": "entry_multiple", 
        "exitMultiple": "exit_multiple",
        "sponsorTargetIRR": "sponsor_target_irr",
        "transactionFeesPct": "transaction_fees_pct",
        "cashToBalanceSheet": "cash_to_balance_sheet",
        "taxRatePct": "tax_rate_pct",
        "allowNegativeEbitda": "allow_negative_ebitda",
    }
    
    # For private companies, allow financial data keys to pass through without validation
    private_financial_keys = {"ltm_ebitda", "ltm_sales", "net_debt"}
    
    # Keys that are handled elsewhere and should be ignored here
    non_assumption_keys = {"purchasePrice", "financialProjections", "sourcesAndUses", 
                          "proFormaCapTable", "returnsAnalysis", "irrSensitivity"}
    
    def deep_merge(base_dict, override_dict, path=""):
        """Recursively merge override dictionary into base dictionary with validation."""
        # Define allowed keys for validation
        allowed_keys = set(base_dict.keys()) | set(key_mapping.keys())
        if is_private:
            allowed_keys.update(private_financial_keys)
        # Allow non-assumption keys to pass through without error
        allowed_keys.update(non_assumption_keys)
        
        for key, value in override_dict.items():
            current_path = f"{path}.{key}" if path else key
            
            # Skip non-assumption sections - they're handled elsewhere
            if key in non_assumption_keys:
                logger.info(f"Skipping non-assumption override section: {key}")
                continue
            
            # Special handling for nested "assumptions" object
            if key == "assumptions" and isinstance(value, dict):
                # For nested assumptions, validate against key_mapping
                for nested_key in value.keys():
                    mapped_nested_key = key_mapping.get(nested_key, nested_key)
                    if nested_key not in key_mapping and mapped_nested_key not in base_dict:
                        raise ValueError(f"Unknown assumption override key: assumptions.{nested_key}")
                
                # Recursively merge nested assumptions
                for assumption_key, assumption_value in value.items():
                    mapped_key = key_mapping.get(assumption_key, assumption_key)
                    base_dict[mapped_key] = assumption_value
                    logger.info(f"Override applied: {current_path}.{assumption_key} = {assumption_value}")
                continue
            
            # Skip validation for private company financial data keys
            if is_private and key in private_financial_keys:
                # These are financial data, not assumptions - don't merge into assumptions
                continue
            
            # Validate assumption keys
            mapped_key = key_mapping.get(key, key)
            if key not in allowed_keys and mapped_key not in allowed_keys:
                raise ValueError(f"Unknown override key: {key}")
            
            # Apply the override
            if isinstance(value, dict) and mapped_key in base_dict and isinstance(base_dict[mapped_key], dict):
                deep_merge(base_dict[mapped_key], value, current_path)
            else:
                base_dict[mapped_key] = value
                logger.info(f"Override applied: {current_path} = {value}")
    
    # Apply overrides with validation
    try:
        deep_merge(assumptions, overrides)
    except ValueError as e:
        logger.error(f"Invalid override provided: {e}")
        raise
    
    return assumptions

def apply_purchase_price_overrides(financial_data: Dict[str, Any], purchase_price_overrides: Dict[str, Any]) -> None:
    """Apply purchase price overrides to financial data."""
    # Map purchase price override keys to financial data keys
    override_mapping = {
        "offerPremiumPct": "offer_premium_pct",
        "basicShares": "basic_shares",
        "currentPricePerShare": "current_share_price",
        "fullyDilutedShares": "fully_diluted_shares"
    }
    
    for key, value in purchase_price_overrides.items():
        if key in override_mapping:
            financial_data_key = override_mapping[key]
            financial_data[financial_data_key] = value
            logger.info(f"Purchase price override applied: {key} = {value}")
        else:
            logger.warning(f"Unknown purchase price override key: {key}")

def calculate_purchase_price(financial_data: Dict[str, Any], assumptions: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate purchase price details using EBITDA-based valuation for realistic LBO analysis."""
    basic_shares = financial_data["basic_shares"]
    current_price = financial_data["current_share_price"]
    # Check for offer premium override, otherwise use default
    offer_premium_pct = financial_data.get("offer_premium_pct", TRANSACTION_ASSUMPTIONS.get("offer_premium_pct", 15.0))
    fully_diluted_shares = financial_data["fully_diluted_shares"]
    ltm_ebitda = financial_data["ltm_ebitda"]
    ltm_sales = financial_data["ltm_sales"]
    net_debt = financial_data["net_debt"]
    
    # Get validation thresholds and constants
    min_price = VALIDATION_THRESHOLDS.get("min_share_price", 0.01)
    min_shares = VALIDATION_THRESHOLDS.get("min_shares_outstanding", 0.01)
    min_sales = VALIDATION_THRESHOLDS.get("min_sales", 0.01)
    min_ev = VALIDATION_THRESHOLDS.get("min_enterprise_value", 1.0)
    revenue_multiple = CALCULATION_CONSTANTS.get("revenue_multiple_for_negative_ebitda", 1.5)
    
    # Cap and validate entry/exit multiples globally
    max_entry_mult = VALIDATION_THRESHOLDS.get("max_entry_multiple", 50.0)
    min_entry_mult = VALIDATION_THRESHOLDS.get("min_entry_multiple", 5.0)
    entry_multiple = max(min_entry_mult, min(assumptions.get("entry_multiple", 12.0), max_entry_mult))
    assumptions["entry_multiple"] = entry_multiple
    
    # Validate inputs to prevent negative values
    current_price = max(min_price, current_price)
    fully_diluted_shares = max(min_shares, fully_diluted_shares)
    ltm_sales = max(min_sales, ltm_sales)
    
    # Handle negative EBITDA companies with revenue-based valuation
    if ltm_ebitda <= 0:
        # Use revenue multiple for unprofitable companies
        enterprise_value = ltm_sales * revenue_multiple
        equity_value = enterprise_value - net_debt
        note_suffix = f"revenue-based valuation ({revenue_multiple}x sales) for unprofitable company"
    else:
        # Use EBITDA-based valuation for profitable companies
        enterprise_value = ltm_ebitda * entry_multiple
        equity_value = enterprise_value - net_debt
        note_suffix = f"EBITDA-based valuation ({entry_multiple}x EBITDA)"
    
    # Ensure enterprise value is positive
    enterprise_value = max(min_ev, enterprise_value)
    
    # Calculate implied price per share based on realistic valuation
    implied_price_per_share = equity_value / fully_diluted_shares if fully_diluted_shares > 0 else 0
    
    # For public companies, offer price should be based on current market price, not implied price
    offer_price_per_share = current_price * (1 + offer_premium_pct / 100)
    equity_offer_price = fully_diluted_shares * offer_price_per_share
    
    # Check for underwater equity situations and warn
    if equity_value <= 0:
        logger.warning(f"PUBLIC COMPANY - Equity underwater at valuation: EV ${enterprise_value:.1f}M - Net Debt ${net_debt:.1f}M = ${equity_value:.1f}M")
        # Still use market-based offer price but flag the issue
        underwater_equity = True
    else:
        underwater_equity = False
    
    # Ensure equity offer price is positive for downstream calculations
    equity_offer_price = max(1.0, equity_offer_price)  # Minimum $1M equity offer price
    
    # Determine if company-specific multiple was used
    is_company_specific = financial_data.get("current_enterprise_multiple") is not None
    current_multiple = financial_data.get("current_enterprise_multiple", "N/A")
    
    if ltm_ebitda <= 0:
        note = f"Using {note_suffix}"
    elif is_company_specific:
        note = f"Using {assumptions['entry_multiple']}x EBITDA entry multiple (based on current {current_multiple:.1f}x EV/EBITDA trading multiple)"
    else:
        note = f"Using {assumptions['entry_multiple']}x EBITDA valuation (default multiple - no current trading data available)"
    
    # Determine display multiple
    if ltm_ebitda <= 0:
        display_multiple = 1.5  # Revenue multiple
    else:
        display_multiple = assumptions["entry_multiple"]  # EBITDA multiple
    
    return {
        "basicShares": basic_shares,
        "currentPricePerShare": current_price,
        "impliedPricePerShare": implied_price_per_share,
        "impliedEquityValue": equity_value,  # Raw equity value (can be negative)
        "underwaterEquity": underwater_equity,  # Flag for underwater equity
        "offerPremiumPct": offer_premium_pct,
        "offerPricePerShare": offer_price_per_share,
        "fullyDilutedShares": fully_diluted_shares,
        "equityOfferPrice": equity_offer_price,
        "enterpriseValue": enterprise_value,
        "entryMultiple": display_multiple,
        "currentTradingMultiple": current_multiple if is_company_specific else None,
        "note": note
    }

def calculate_purchase_price_private(financial_data: Dict[str, Any], assumptions: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate purchase price for private companies - UNIFIED structure with share equivalents for frontend consistency."""
    ltm_ebitda = financial_data["ltm_ebitda"]
    ltm_sales = financial_data["ltm_sales"]
    net_debt = financial_data["net_debt"]
    
    # Get entry multiple with validation
    max_entry_mult = VALIDATION_THRESHOLDS.get("max_entry_multiple", 50.0)
    min_entry_mult = VALIDATION_THRESHOLDS.get("min_entry_multiple", 5.0)
    entry_multiple = max(min_entry_mult, min(assumptions.get("entry_multiple", 8.0), max_entry_mult))
    assumptions["entry_multiple"] = entry_multiple
    
    # Calculate enterprise value using EBITDA multiple (or sales for negative EBITDA)
    if ltm_ebitda <= 0:
        # Use revenue multiple for unprofitable companies
        revenue_multiple = CALCULATION_CONSTANTS.get("revenue_multiple_for_negative_ebitda", 1.5)
        enterprise_value = ltm_sales * revenue_multiple
        logger.warning(f"PRIVATE COMPANY - Using revenue-based valuation: {ltm_sales:.1f} x {revenue_multiple} = {enterprise_value:.1f}")
    else:
        # Use EBITDA-based valuation for profitable companies
        enterprise_value = ltm_ebitda * entry_multiple
    
    # Calculate equity value (can be negative if highly leveraged)
    equity_value = enterprise_value - net_debt
    
    # Warn if equity is underwater at entry
    if equity_value <= 0:
        logger.warning(f"PRIVATE COMPANY - Equity underwater at entry: EV ${enterprise_value:.1f}M - Net Debt ${net_debt:.1f}M = ${equity_value:.1f}M")
        underwater_equity = True
    else:
        underwater_equity = False
    
    # UNIFIED APPROACH: Create share-equivalent data for frontend consistency
    # Use a "unit" system: 1 million units = total equity value
    # This makes private companies look like public companies to the frontend
    
    # Simulate share data using units (millions)
    basic_shares_equiv = 1.0  # 1 million units as base
    offer_premium_pct = financial_data.get("offer_premium_pct", TRANSACTION_ASSUMPTIONS.get("offer_premium_pct", 15.0))
    
    # Calculate "current price per unit" - what each unit would be worth at current valuation
    current_price_per_unit = equity_value / basic_shares_equiv if basic_shares_equiv > 0 else 0
    
    # Calculate offer price per unit (with premium)
    offer_price_per_unit = current_price_per_unit * (1 + offer_premium_pct / 100)
    
    # Use same shares for fully diluted (no dilution in private companies typically)
    fully_diluted_shares_equiv = basic_shares_equiv
    
    # Calculate implied price per unit based on EBITDA valuation (same as current for private)
    implied_price_per_unit = current_price_per_unit
    
    # Total equity offer price
    equity_offer_price = max(0.1, equity_value * (1 + offer_premium_pct / 100))
    
    # Return UNIFIED structure that matches public companies
    return {
        # Share-equivalent fields (NEW - matches public structure)
        "basicShares": basic_shares_equiv,
        "currentPricePerShare": current_price_per_unit,
        "impliedPricePerShare": implied_price_per_unit,
        "offerPremiumPct": offer_premium_pct,
        "offerPricePerShare": offer_price_per_unit,
        "fullyDilutedShares": fully_diluted_shares_equiv,
        "equityOfferPrice": equity_offer_price,
        
        # Enterprise-level fields (consistent with public)
        "enterpriseValue": enterprise_value,
        "entryMultiple": entry_multiple,
        "currentTradingMultiple": None,  # N/A for private companies
        "note": f"Private company valuation using {entry_multiple:.1f}x EBITDA multiple (units represent $M equity value)",
        
        # Private-specific fields (kept for backward compatibility)
        "equityValue": equity_value,  # Raw equity value (can be negative)
        "underwaterEquity": underwater_equity,  # Flag for underwater equity
    }

def calculate_sources_and_uses(purchase_price: Dict[str, Any], assumptions: Dict[str, Any], 
                             debt_amounts: Dict[str, Any], financial_data: Dict[str, Any], is_private: bool = False) -> Dict[str, Any]:
    """Calculate sources and uses of funds - UNIFIED structure with consistent labels."""
    equity_offer_price = purchase_price["equityOfferPrice"]
    
    # Calculate enterprise value for transaction fees
    if is_private:
        enterprise_value = purchase_price["enterpriseValue"]
    else:
        enterprise_value = equity_offer_price + financial_data["net_debt"]
    
    # Uses - ensure all uses are positive with guarded defaults
    refinancing_net_debt = max(0, financial_data.get("net_debt", 0))
    cash_to_balance_sheet = max(0, assumptions.get("cash_to_balance_sheet", 500.0))
    transaction_fees_pct = assumptions.get("transaction_fees_pct", 1.5)
    transaction_fees = max(0, enterprise_value * (transaction_fees_pct / 100))
    
    total_uses = equity_offer_price + refinancing_net_debt + cash_to_balance_sheet + transaction_fees
    
    # Sources - use calculated debt amounts
    first_lien_amount = max(0, debt_amounts["first_lien"])  # Cannot be negative
    second_lien_amount = max(0, debt_amounts["second_lien"])  # Cannot be negative
    mezzanine_amount = max(0, debt_amounts["mezzanine"])  # Cannot be negative
    
    total_debt = first_lien_amount + second_lien_amount + mezzanine_amount
    equity_investment = total_uses - total_debt
    
    # Critical validation: Ensure sponsor equity is positive
    if equity_investment <= 0:
        logger.warning(f"Negative sponsor equity detected: ${equity_investment or 0:.1f}M. Adjusting debt structure.")
        # Reduce debt to ensure positive sponsor equity (minimum % of total uses)
        min_equity_pct = CALCULATION_CONSTANTS.get("min_sponsor_equity_pct", 10.0)
        min_sponsor_equity = total_uses * (min_equity_pct / 100)
        max_total_debt = total_uses - min_sponsor_equity
        
        # Scale down debt proportionally
        debt_scale_factor = max_total_debt / max(total_debt, 0.01)  # Avoid division by zero
        if debt_scale_factor < 1:
            first_lien_amount = first_lien_amount * debt_scale_factor
            second_lien_amount = second_lien_amount * debt_scale_factor
            mezzanine_amount = mezzanine_amount * debt_scale_factor
            total_debt = first_lien_amount + second_lien_amount + mezzanine_amount
            equity_investment = total_uses - total_debt
            logger.info(f"Adjusted debt structure - new sponsor equity: ${equity_investment or 0:.1f}M")
      
    # Final validation: Ensure equity investment meets minimum
    min_sponsor_equity = VALIDATION_THRESHOLDS.get("min_sponsor_equity", 1.0)
    equity_investment = max(min_sponsor_equity, equity_investment)
    
    # UNIFIED APPROACH: Always show all debt tranches consistently
    sources = [
        {"label": "First Lien Term Loan", "amount": first_lien_amount},
        {"label": "Second Lien", "amount": second_lien_amount},
        {"label": "Mezzanine", "amount": mezzanine_amount},
        {"label": "Equity Investment", "amount": equity_investment}
    ]
    
    # UNIFIED APPROACH: Use consistent "Purchase Price" label for both public and private
    uses = [
        {"label": "Purchase Price", "amount": equity_offer_price},
        {"label": "Refinancing Net Debt", "amount": refinancing_net_debt},
        {"label": "Cash to Balance Sheet", "amount": cash_to_balance_sheet},
        {"label": "Transaction Fees", "amount": transaction_fees}
    ]
    
    return {
        "sources": sources,
        "uses": uses,
        "totalSources": sum(s["amount"] for s in sources),
        "totalUses": sum(u["amount"] for u in uses)
    }

def build_pro_forma_cap_table(sources_uses: Dict[str, Any], financial_data: Dict[str, Any], 
                            assumptions: Dict[str, Any], debt_amounts: Dict[str, Any], is_private: bool = False) -> Dict[str, Any]:
    """Build pro forma capitalization table - UNIFIED structure for both public and private companies."""
    ltm_ebitda = financial_data["ltm_ebitda"]
    cash = max(0, assumptions["cash_to_balance_sheet"])  # Cannot be negative
    
    # Get debt amounts from sources - ensure all are positive
    first_lien_amount = max(0, debt_amounts["first_lien"])
    second_lien_amount = max(0, debt_amounts["second_lien"])
    mezzanine_amount = max(0, debt_amounts["mezzanine"])
    
    # Find sponsor equity amount safely
    sponsor_equity_amount = 0
    for source in sources_uses["sources"]:
        if "Equity" in source["label"]:
            sponsor_equity_amount = max(0, source["amount"])  # Cannot be negative
            break
    
    # Ensure minimum sponsor equity
    sponsor_equity_amount = max(1.0, sponsor_equity_amount)  # Minimum $1M
    
    # UNIFIED APPROACH: Always include all debt tranches for consistent frontend display
    total_capitalization = first_lien_amount + second_lien_amount + mezzanine_amount + sponsor_equity_amount
    
    # Calculate percentages safely (avoid division by zero)
    if total_capitalization > 0:
        first_lien_pct = (first_lien_amount / total_capitalization) * 100
        second_lien_pct = (second_lien_amount / total_capitalization) * 100
        mezzanine_pct = (mezzanine_amount / total_capitalization) * 100
        sponsor_equity_pct = (sponsor_equity_amount / total_capitalization) * 100
    else:
        # Fallback percentages if total capitalization is somehow zero
        first_lien_pct = second_lien_pct = mezzanine_pct = sponsor_equity_pct = 0.0
    
    # Handle EBITDA multiple calculations safely
    if ltm_ebitda > 0.01:  # Minimum positive EBITDA for meaningful multiples
        first_lien_multiple = first_lien_amount / ltm_ebitda
        cumulative_second_lien_multiple = (first_lien_amount + second_lien_amount) / ltm_ebitda
        total_debt_multiple = (first_lien_amount + second_lien_amount + mezzanine_amount) / ltm_ebitda
    else:
        # Use 0 for negative or very small EBITDA cases
        first_lien_multiple = 0.0
        cumulative_second_lien_multiple = 0.0
        total_debt_multiple = 0.0
    
    # Return UNIFIED structure - always show all debt tranches
    return {
        "cash": cash,
        "firstLienTermLoan": {
            "amount": first_lien_amount,
            "pctOfCapital": first_lien_pct,
            "cumulativeMultipleOfEBITDA": first_lien_multiple
        },
        "secondLien": {
            "amount": second_lien_amount,
            "pctOfCapital": second_lien_pct,
            "cumulativeMultipleOfEBITDA": cumulative_second_lien_multiple
        },
        "mezzanine": {
            "amount": mezzanine_amount,
            "pctOfCapital": mezzanine_pct,
            "cumulativeMultipleOfEBITDA": total_debt_multiple
        },
        "sponsorEquity": {
            "amount": sponsor_equity_amount,
            "pctOfCapital": sponsor_equity_pct
        },
        "totalCapitalization": total_capitalization,
        "ltmUnleveredEBITDA": ltm_ebitda
    }

def generate_financial_projections(financial_data: Dict[str, Any], assumptions: Dict[str, Any], 
                                 debt_amounts: Dict[str, Any], financial_projections_overrides: List[Dict[str, Any]] = []) -> List[Dict[str, Any]]:
    """Generate financial projections for base year + 5 years with realistic growth and debt service."""
    base_year = assumptions.get("base_year", 2025)
    base_sales = financial_data["ltm_sales"]
    ltm_ebitda = financial_data["ltm_ebitda"]
    
    # Get projection parameters with guarded defaults
    sales_growth_rate = OPERATING_ASSUMPTIONS.get("sales_growth_rates", [4.5, 4.5, 4.5, 4.5, 4.5])[0]
    ebitda_growth_rate = 5.0  # Conservative 5% annual EBITDA growth
    da_pct_of_sales = OPERATING_ASSUMPTIONS.get("d_and_a_pct_of_sales", 3.0)
    capex_pct_of_sales = OPERATING_ASSUMPTIONS.get("capex_pct_of_sales", 0.5)
    nwc_pct_of_sales = OPERATING_ASSUMPTIONS.get("nwc_pct_of_sales", 0.5)
    tax_rate_pct = assumptions.get("tax_rate_pct", 27.0)
    
    # Debt tracking - start with total debt from sources
    total_initial_debt = debt_amounts.get("total_debt", 0)
    blended_interest_rate = CALCULATION_CONSTANTS.get("blended_interest_rate", 7.0)
    
    # Initialize debt balance tracking
    gross_debt_balance = total_initial_debt
    cash_balance = assumptions.get("cash_to_balance_sheet", 500.0)
    
    # Get calculation constants
    min_ebitda_margin = CALCULATION_CONSTANTS.get("min_ebitda_target_margin", 5.0)
    min_ebitda_absolute = CALCULATION_CONSTANTS.get("min_ebitda_target_absolute", 50.0)
    ebitda_growth_negative = CALCULATION_CONSTANTS.get("ebitda_growth_for_negative_companies", 15.0)
    
    projections = []
    prev_nwc = base_sales * (nwc_pct_of_sales / 100)
    
    # Extract override parameters for sales growth and EBITDA margins by year
    growth_overrides = {}
    margin_overrides = {}
    for override in financial_projections_overrides:
        if "year" in override:
            year_key = override["year"]
            if "salesGrowthPct" in override:
                growth_overrides[year_key] = override["salesGrowthPct"]
            if "ebitdaMarginPct" in override:
                margin_overrides[year_key] = override["ebitdaMarginPct"]
    
    for i in range(6):  # Base year + 5 projection years
        year = base_year + i
        
        if i == 0:
            # Base year - use LTM data as starting point
            sales = base_sales
            sales_growth = None
            
            # Handle negative EBITDA companies - assume path to profitability
            if ltm_ebitda <= 0:
                # Assume company reaches target EBITDA margin in year 1
                ebitda = max(sales * (min_ebitda_margin / 100), min_ebitda_absolute)
            else:
                # Project 2025 EBITDA at +5% over LTM (not re-using LTM)
                ebitda = ltm_ebitda * (1 + ebitda_growth_rate / 100)
            
            # Apply base year margin override if provided
            if year in margin_overrides:
                ebitda = sales * (margin_overrides[year] / 100)
                logger.info(f"Applied EBITDA margin override for {year}: {margin_overrides[year]:.1f}%")
                
        else:
            # Projection years - check for growth rate overrides
            if year in growth_overrides:
                custom_growth_rate = growth_overrides[year]
                sales = projections[i-1]["sales"] * (1 + custom_growth_rate / 100)
                sales_growth = custom_growth_rate
                logger.info(f"Applied sales growth override for {year}: {custom_growth_rate:.1f}%")
            else:
                # Use default growth rate
                sales = projections[i-1]["sales"] * (1 + sales_growth_rate / 100)
                sales_growth = sales_growth_rate
            
            # EBITDA calculation - check for margin overrides first
            if year in margin_overrides:
                custom_margin = margin_overrides[year]
                ebitda = sales * (custom_margin / 100)
                logger.info(f"Applied EBITDA margin override for {year}: {custom_margin:.1f}%")
            else:
                # Default EBITDA growth logic
                if ltm_ebitda <= 0:
                    # Aggressive EBITDA improvement for loss-making companies
                    ebitda = projections[0]["ebitda"] * ((1 + ebitda_growth_negative / 100) ** i)  # 15% EBITDA growth
                else:
                    # EBITDA grows at 5% annually from 2025 base
                    ebitda = projections[0]["ebitda"] * ((1 + ebitda_growth_rate / 100) ** i)
        
        # Income statement calculations
        da = sales * (da_pct_of_sales / 100)
        ebit = ebitda - da  # Correct EBIT calculation
        
        # Balance sheet items
        capex = sales * (capex_pct_of_sales / 100)
        nwc = sales * (nwc_pct_of_sales / 100)
        delta_nwc = nwc - prev_nwc if i > 0 else 0
        prev_nwc = nwc
        
        # Store beginning debt balance for interest calculation
        beginning_debt_balance = gross_debt_balance
        
        # Calculate interest expense on beginning-of-year debt balance (initial calculation)
        cash_interest = gross_debt_balance * (blended_interest_rate / 100)
        
        # Taxes on EBT (EBIT - Interest)
        ebt = max(0, ebit - cash_interest)  # Earnings before tax
        cash_taxes = ebt * (tax_rate_pct / 100)
        
        # Free cash flow calculation
        fcf_ebitda = ebitda
        fcf_capex = capex
        fcf_delta_nwc = delta_nwc
        fcf_interest = cash_interest
        fcf_taxes = cash_taxes
        fcf_for_debt_repayment = fcf_ebitda - fcf_capex - fcf_delta_nwc - fcf_interest - fcf_taxes
        
        # Debt paydown (use FCF to pay down debt) - remove artificial 5% cap
        if i > 0 and fcf_for_debt_repayment > 0:
            # Sweep all excess FCF to pay down debt
            debt_paydown = max(0, fcf_for_debt_repayment)
            gross_debt_balance = max(0, gross_debt_balance - debt_paydown)  # Ensure debt doesn't go negative
        else:
            debt_paydown = 0
        
        # Recalculate interest expense on AVERAGE debt balance for more accurate modeling
        # This better reflects reality as interest accrues throughout the year as debt is paid down
        if i > 0 and debt_paydown > 0:
            average_debt_balance = (beginning_debt_balance + gross_debt_balance) / 2
            cash_interest = average_debt_balance * (blended_interest_rate / 100)
            
            # Recalculate taxes with corrected interest
            ebt = max(0, ebit - cash_interest)
            cash_taxes = ebt * (tax_rate_pct / 100)
            
            # Update FCF components with corrected interest and taxes
            fcf_interest = cash_interest
            fcf_taxes = cash_taxes
            fcf_for_debt_repayment = fcf_ebitda - fcf_capex - fcf_delta_nwc - fcf_interest - fcf_taxes
        
        # Net debt calculation
        net_debt = gross_debt_balance - cash_balance
        
        projection = {
            "year": year,
            "sales": sales,
            "salesGrowthPct": sales_growth,
            "ebitda": ebitda,
            "ebitdaMarginPct": (ebitda / sales * 100) if sales > 0 else None,
            "ebit": ebit,
            "ebitMarginPct": (ebit / sales * 100) if sales > 0 else None,
            "dAndA": da,
            "dAndAAsPctOfSales": (da / sales * 100) if sales > 0 else None,
            "capex": capex,
            "capexAsPctOfSales": (capex / sales * 100) if sales > 0 else None,
            "netWorkingCapital": nwc,
            "nwcAsPctOfSales": (nwc / sales * 100) if sales > 0 else None,
            "grossDebt": gross_debt_balance,
            "cashBalance": cash_balance,
            "netDebt": net_debt,
            "freeCashFlow": {
                "ebitda": fcf_ebitda,
                "lessCapex": fcf_capex,
                "lessIncreaseInNWC": fcf_delta_nwc,
                "lessCashInterest": fcf_interest,
                "lessCashTaxes": fcf_taxes,
                "fCFForDebtRepayment": fcf_for_debt_repayment,
                "debtPaydown": debt_paydown if i > 0 else 0
            }
        }
        
        # Apply any remaining financial projections overrides (for non-calculated fields)
        if financial_projections_overrides:
            for override in financial_projections_overrides:
                if "year" in override and override["year"] == year:
                    for key, value in override.items():
                        if key not in ["year", "salesGrowthPct", "ebitdaMarginPct"]:  # Skip already handled overrides
                            projection[key] = value
        
        projections.append(projection)
    
    return projections

def calculate_returns_analysis(projections: List[Dict[str, Any]], cap_table: Dict[str, Any], 
                             assumptions: Dict[str, Any], debt_amounts: Dict[str, Any], is_private: bool = False) -> Dict[str, Any]:
    """Calculate returns analysis and IRR with realistic debt paydown."""
    # Terminal year (last projection)
    terminal_projection = projections[-1]
    terminal_ebitda = max(VALIDATION_THRESHOLDS.get("min_sales", 0.01), terminal_projection["ebitda"])
    exit_multiple = max(VALIDATION_THRESHOLDS.get("min_exit_multiple", 5.0), 
                       min(assumptions.get("exit_multiple", 12.0), VALIDATION_THRESHOLDS.get("max_exit_multiple", 50.0)))
    
    # Calculate enterprise value at exit
    enterprise_value = terminal_ebitda * exit_multiple
    
    # Use actual projected net debt from debt schedule
    remaining_net_debt = terminal_projection["netDebt"]
    
    # Equity value at exit - ensure it's positive
    min_equity_value = VALIDATION_THRESHOLDS.get("min_equity_offer_price", 1.0)
    equity_value_at_exit = max(min_equity_value, enterprise_value - remaining_net_debt)
    
    # Sponsor ownership and returns
    sponsor_ownership_pct = max(0.1, min(100.0, TRANSACTION_ASSUMPTIONS.get("sponsor_ownership_pct", 95.0)))
    sponsor_equity_value_at_exit = equity_value_at_exit * (sponsor_ownership_pct / 100)
    sponsor_equity_value_at_closing = max(VALIDATION_THRESHOLDS.get("min_sponsor_equity", 1.0), 
                                        cap_table["sponsorEquity"]["amount"])
    
    # Calculate IRR safely (5-year hold period)
    hold_period = CALCULATION_CONSTANTS.get("hold_period_years", 5)
    if sponsor_equity_value_at_closing > 0.01:  # Avoid very small values
        multiple = sponsor_equity_value_at_exit / sponsor_equity_value_at_closing
        # Ensure multiple is positive and reasonable
        multiple = max(0.01, min(100.0, multiple))  # Cap between 0.01x and 100x
        
        try:
            irr = (multiple ** (1/hold_period) - 1) * 100
        except Exception:
            irr = -100.0
        
        # Check for NaN and validate result
        if math.isnan(irr):
            irr = -100.0
        
        # Cap IRR within reasonable bounds
        max_irr = VALIDATION_THRESHOLDS.get("max_irr", 1000.0)
        min_irr = VALIDATION_THRESHOLDS.get("min_irr", -100.0)
        irr = max(min_irr, min(irr, max_irr))
    else:
        irr = -100.0  # No investment means total loss
    
    # Check for underwater equity at entry and add warning
    irr_warning = None
    if sponsor_equity_value_at_closing <= 0 or equity_value_at_exit <= remaining_net_debt:
        irr_warning = "Equity underwater at entry"
        logger.warning(f"Returns analysis warning: {irr_warning}")
    
    returns = {
        "terminalEBITDA": terminal_ebitda,
        "exitMultiple": exit_multiple,
        "enterpriseValue": enterprise_value,
        "lessNetDebt": remaining_net_debt,
        "equityValueAtExit": equity_value_at_exit,
        "sponsorOwnershipPctAtExit": sponsor_ownership_pct,
        "sponsorEquityValueAtExit": sponsor_equity_value_at_exit,
        "sponsorEquityValueAtClosing": sponsor_equity_value_at_closing,
        "IRR": irr,
        "debtPaydownSummary": {
            "initialGrossDebt": debt_amounts["total_debt"],
            "finalGrossDebt": terminal_projection["grossDebt"],
            "totalDebtPaydown": debt_amounts["total_debt"] - terminal_projection["grossDebt"],
            "initialNetDebt": debt_amounts["total_debt"] - assumptions["cash_to_balance_sheet"],
            "finalNetDebt": remaining_net_debt
        }
    }
    
    # Add warning if applicable
    if irr_warning:
        returns["warning"] = irr_warning
    
    return returns

async def generate_irr_sensitivity(financial_data: Dict[str, Any], assumptions: Dict[str, Any], 
                                 ticker: str, session: AsyncSession, is_private: bool = False) -> Dict[str, Any]:
    """
    Generate IRR sensitivity analysis - UNIFIED structure for both public and private companies.
    
    Y-axis: Sponsor Required IRR %
    X-axis: EBITDA Exit Multiple
    Cell values: Always includes both equity value per share AND total equity value for consistency
    """
    sponsor_required_irrs = SENSITIVITY_PARAMS["sponsor_required_irrs"]
    
    # Use company-specific exit multiples if enterprise multiple is available
    if "current_enterprise_multiple" in financial_data and financial_data["current_enterprise_multiple"]:
        company_params = generate_company_specific_sensitivity_params(financial_data["current_enterprise_multiple"])
        exit_multiples = company_params["exit_multiples"]
        logger.info(f"Using company-specific exit multiples for sensitivity: {exit_multiples}")
    else:
        # Fallback to default exit multiples
        exit_multiples = SENSITIVITY_PARAMS["exit_multiples"]
        logger.info(f"Using default exit multiples for sensitivity: {exit_multiples}")
    
    # Get key data needed for calculations
    ltm_ebitda = financial_data["ltm_ebitda"]
    
    # UNIFIED APPROACH: Always calculate share equivalents for consistent frontend display
    if is_private:
        # For private companies, use the unit system from purchase price calculation
        fully_diluted_shares = 1.0  # 1 million units (same as purchase price)
    else:
        fully_diluted_shares = financial_data["fully_diluted_shares"]
    
    debt_amounts = get_debt_amounts(ltm_ebitda)
    
    # Calculate purchase price and other components needed
    if is_private:
        purchase_price = calculate_purchase_price_private(financial_data, assumptions)
    else:
        purchase_price = calculate_purchase_price(financial_data, assumptions)
    
    sources_uses = calculate_sources_and_uses(purchase_price, assumptions, debt_amounts, financial_data, is_private)
    cap_table = build_pro_forma_cap_table(sources_uses, financial_data, assumptions, debt_amounts, is_private)
    projections = generate_financial_projections(financial_data, assumptions, debt_amounts)
    
    # Get key metrics for sensitivity calculation
    terminal_projection = projections[-1]
    terminal_ebitda = terminal_projection["ebitda"]
    remaining_net_debt = terminal_projection["netDebt"]
    sponsor_equity_at_closing = cap_table["sponsorEquity"]["amount"]
    sponsor_ownership_pct = TRANSACTION_ASSUMPTIONS["sponsor_ownership_pct"]
    hold_period = 5  # years
    
    # Build sensitivity matrix
    matrix = []
    
    for required_irr in sponsor_required_irrs:
        row = []
        for exit_mult in exit_multiples:
            try:
                # Calculate enterprise value at exit
                enterprise_value_at_exit = terminal_ebitda * exit_mult
                
                # Calculate total equity value at exit (EV - Net Debt)
                total_equity_value_at_exit = enterprise_value_at_exit - remaining_net_debt
                
                # Calculate sponsor equity value at exit
                sponsor_equity_at_exit = total_equity_value_at_exit * (sponsor_ownership_pct / 100)
                
                # Calculate the required sponsor equity at closing to achieve the target IRR
                # Required Multiple = (1 + IRR)^years
                # So: Required Closing Equity = Exit Value / Required Multiple
                required_multiple = (1 + required_irr / 100) ** hold_period
                required_sponsor_equity_at_closing = sponsor_equity_at_exit / required_multiple
                
                # Calculate total required equity at closing
                required_total_equity_at_closing = required_sponsor_equity_at_closing / (sponsor_ownership_pct / 100)
                
                # UNIFIED APPROACH: Always provide both per-share and total values
                equity_value_per_share = required_total_equity_at_closing / fully_diluted_shares
                
                # Store BOTH per share and total values for consistent frontend handling
                cell_value = {
                    "equityValuePerShare": round(equity_value_per_share, 2),
                    "totalEquityValue": round(total_equity_value_at_exit, 0),
                    "impliedNetDebt": round(remaining_net_debt, 0),
                    "enterpriseValue": round(enterprise_value_at_exit, 0),
                    "requiredEquityAtClosing": round(required_total_equity_at_closing, 0)
                }
                
                row.append(cell_value)
                
            except (ZeroDivisionError, ValueError):
                # Handle edge cases - always provide both fields
                cell_value = {
                    "equityValuePerShare": 0.0,
                    "totalEquityValue": 0.0,
                    "impliedNetDebt": 0.0,
                    "enterpriseValue": 0.0,
                    "requiredEquityAtClosing": 0.0
                }
                row.append(cell_value)
        
        matrix.append(row)
    
    # UNIFIED APPROACH: Consistent note text for both company types
    note_text = f"Matrix shows required equity values at closing needed to achieve target sponsor IRR at given exit multiple. For private companies, 'per share' represents per $1M unit of equity value."
    
    return {
        "sponsorRequiredIRRs": sponsor_required_irrs,
        "exitMultiples": exit_multiples,
        "matrix": matrix,
        "assumptions": {
            "holdPeriod": hold_period,
            "sponsorOwnershipPct": sponsor_ownership_pct,
            "terminalEBITDA": terminal_ebitda,
            "sponsorEquityAtClosing": sponsor_equity_at_closing,
            "fullyDilutedShares": fully_diluted_shares
        },
        "note": note_text
    }

def generate_company_specific_sensitivity_params(enterprise_multiple: float) -> Dict[str, List[float]]:
    """
    Generate company-specific sensitivity parameters based on actual enterprise multiple.
    Handles negative EV/EBITDA multiples for unprofitable companies.
    
    Args:
        enterprise_multiple: Current EV/EBITDA multiple from market data
        
    Returns:
        Dictionary with adjusted sensitivity parameters
    """
    # Handle negative or unrealistic multiples (negative EBITDA companies)
    if enterprise_multiple < 0 or enterprise_multiple > 100.0:
        logger.warning(f"Unrealistic enterprise multiple ({enterprise_multiple:.1f}x) - using growth company defaults")
        # Use revenue-based valuation for unprofitable companies
        entry_multiple = 12.0  # Reasonable entry multiple for growth companies
        exit_multiples = [10.0, 12.0, 14.0, 16.0, 18.0]  # Growth exit range
        
        return {
            "entry_multiple": entry_multiple,
            "exit_multiples": exit_multiples,
            "sponsor_required_irrs": [15.0, 20.0, 25.0, 30.0, 35.0]
        }
    
    # Validate and cap extreme multiples for LBO analysis
    if enterprise_multiple > 50.0:
        logger.warning(f"Very high enterprise multiple ({enterprise_multiple:.1f}x) - capping at 50x for LBO analysis")
        enterprise_multiple = 50.0
    elif enterprise_multiple < 5.0:
        logger.warning(f"Very low enterprise multiple ({enterprise_multiple:.1f}x) - using minimum 5x for LBO analysis")
        enterprise_multiple = 5.0
    
    # Base the entry multiple on current trading multiple (with LBO discount)
    # More aggressive discount for very high multiples
    if enterprise_multiple > 30.0:
        discount_factor = 0.75  # 25% discount for very high multiples
    elif enterprise_multiple > 20.0:
        discount_factor = 0.80  # 20% discount for high multiples
    else:
        discount_factor = 0.85  # 15% discount for normal multiples
    
    entry_multiple = max(enterprise_multiple * discount_factor, 8.0)  # Minimum 8x entry
    
    # Cap entry multiple at reasonable LBO range
    if entry_multiple > 35.0:
        logger.warning(f"Very high entry multiple ({entry_multiple:.1f}x) - capping at 35x for LBO feasibility")
        entry_multiple = 35.0
    
    # Generate exit multiples around the entry multiple
    exit_multiples = [
        round(entry_multiple * 0.9, 1),    # 10% down
        round(entry_multiple * 1.0, 1),    # Same as entry
        round(entry_multiple * 1.1, 1),    # 10% up
        round(entry_multiple * 1.2, 1),    # 20% up
        round(entry_multiple * 1.3, 1)     # 30% up
    ]
    
    # Sponsor required IRRs remain consistent
    sponsor_required_irrs = [15.0, 20.0, 25.0, 30.0, 35.0]
    
    logger.info(f"Generated company-specific sensitivity params:")
    logger.info(f"  Current EV/EBITDA: {enterprise_multiple:.1f}x")
    logger.info(f"  Entry multiple: {entry_multiple:.1f}x (discount: {(1-discount_factor)*100:.0f}%)")
    logger.info(f"  Exit multiples: {exit_multiples}")
    
    return {
        "entry_multiple": entry_multiple,
        "exit_multiples": exit_multiples,
        "sponsor_required_irrs": sponsor_required_irrs
    } 