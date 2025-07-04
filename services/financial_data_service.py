import aiohttp
import asyncio
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Financial Modeling Prep API configuration
FMP_API_KEY = "fjRDKKnsRnVNMfFepDM6ox31u9RlPklv"
FMP_BASE_URL = "https://financialmodelingprep.com/stable"

async def get_stock_quote(symbol: str) -> Dict[str, Any]:
    """Get current stock quote data from Financial Modeling Prep."""
    url = f"{FMP_BASE_URL}/quote?symbol={symbol}&apikey={FMP_API_KEY}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and len(data) > 0:
                        quote = data[0]
                        return {
                            "symbol": quote.get("symbol"),
                            "name": quote.get("name"),
                            "price": quote.get("price", 0),
                            "market_cap": quote.get("marketCap", 0),
                            "shares_outstanding": quote.get("marketCap", 0) / quote.get("price", 1) if quote.get("price", 0) > 0 else 0,
                            "volume": quote.get("volume", 0),
                            "year_high": quote.get("yearHigh", 0),
                            "year_low": quote.get("yearLow", 0)
                        }
                else:
                    logger.error(f"FMP API error for {symbol}: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Error fetching quote for {symbol}: {e}")
        return None

async def get_ttm_income_statement(symbol: str) -> Dict[str, Any]:
    """Get TTM income statement from Financial Modeling Prep."""
    url = f"{FMP_BASE_URL}/income-statement-ttm?symbol={symbol}&apikey={FMP_API_KEY}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and len(data) > 0:
                        # Take the most recent TTM data (first item)
                        ttm_data = data[0]
                        return parse_ttm_income_statement(ttm_data)
                    else:
                        logger.error(f"No TTM data found for {symbol}")
                        return None
                else:
                    logger.error(f"FMP API error for {symbol} TTM financials: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Error fetching TTM financials for {symbol}: {e}")
        return None

def parse_ttm_income_statement(data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse TTM income statement data to extract key metrics."""
    try:
        # Extract key metrics directly from TTM data
        result = {
            "revenue": data.get("revenue", 0),
            "ebitda": data.get("ebitda", 0),
            "ebit": data.get("operatingIncome", 0),  # Operating income is EBIT
            "net_income": data.get("netIncome", 0),
            "depreciation_amortization": data.get("depreciationAndAmortization", 0),
            "interest_expense": data.get("interestExpense", 0),
            "tax_expense": data.get("incomeTaxExpense", 0),
            "effective_tax_rate": 0.15  # Default fallback
        }
        
        # Calculate effective tax rate
        income_before_tax = data.get("incomeBeforeTax", 0)
        if income_before_tax > 0 and result["tax_expense"] > 0:
            result["effective_tax_rate"] = result["tax_expense"] / income_before_tax
        
        # For now, we'll estimate debt and cash from other endpoints or use reasonable defaults
        # These could be fetched from balance sheet endpoint if needed
        estimated_market_cap = data.get("weightedAverageShsOutDil", 15000000000) * 200  # Rough estimate
        result.update({
            "total_debt": estimated_market_cap * 0.1,  # Assume 10% of market cap in debt
            "cash_and_equivalents": estimated_market_cap * 0.05,  # Assume 5% of market cap in cash
            "capex": result["revenue"] * 0.03,  # Assume 3% of revenue for capex
        })
        
        result["net_debt"] = max(0, result["total_debt"] - result["cash_and_equivalents"])
        
        return result
        
    except Exception as e:
        logger.error(f"Error parsing TTM income statement: {e}")
        return None

async def get_comprehensive_financial_data(symbol: str) -> Dict[str, Any]:
    """Get comprehensive financial data combining quote, TTM income statement, and enterprise multiples."""
    try:
        # Fetch quote, TTM financial data, and enterprise multiples concurrently
        quote_task = get_stock_quote(symbol)
        financials_task = get_ttm_income_statement(symbol)
        ratios_task = get_enterprise_multiples(symbol)
        
        quote_data, financial_data, ratios_data = await asyncio.gather(quote_task, financials_task, ratios_task)
        
        if not quote_data:
            raise ValueError(f"Could not fetch quote data for {symbol}")
        
        # Use quote data as base
        result = {
            "symbol": symbol,
            "current_share_price": quote_data["price"],
            "market_cap": quote_data["market_cap"],
            "shares_outstanding": quote_data["shares_outstanding"],
            "basic_shares": quote_data["shares_outstanding"] / 1_000_000,  # Convert to millions
            "fully_diluted_shares": quote_data["shares_outstanding"] * 1.03 / 1_000_000,  # Assume 3% dilution
        }
        
        # Add financial data if available
        if financial_data:
            result.update({
                "ltm_sales": financial_data["revenue"] / 1_000_000,  # Convert to millions
                "ltm_ebitda": financial_data["ebitda"] / 1_000_000,
                "ltm_ebit": financial_data["ebit"] / 1_000_000,
                "net_debt": financial_data["net_debt"] / 1_000_000,
                "total_debt": financial_data["total_debt"] / 1_000_000,
                "cash_and_equivalents": financial_data["cash_and_equivalents"] / 1_000_000,
                "capex": financial_data["capex"] / 1_000_000,
                "depreciation_amortization": financial_data["depreciation_amortization"] / 1_000_000,
                "interest_expense": financial_data["interest_expense"] / 1_000_000,
                "effective_tax_rate": financial_data["effective_tax_rate"] * 100  # Convert to percentage
            })
        
        # Add enterprise multiple and ratios data if available
        if ratios_data and ratios_data.get("enterprise_value_multiple"):
            result.update({
                "current_enterprise_multiple": ratios_data["enterprise_value_multiple"],
                "price_to_earnings_ratio": ratios_data.get("price_to_earnings_ratio"),
                "price_to_sales_ratio": ratios_data.get("price_to_sales_ratio"),
                "ebitda_margin_pct": ratios_data.get("ebitda_margin", 0) * 100 if ratios_data.get("ebitda_margin") else None
            })
        else:
            # Use reasonable estimates for mega-cap companies if financial data unavailable
            logger.warning(f"Using estimated financial data for {symbol}")
            estimated_ebitda = result["market_cap"] * 0.03  # Assume 3% EBITDA yield
            result.update({
                "ltm_sales": estimated_ebitda * 3.5,  # Assume ~30% EBITDA margin
                "ltm_ebitda": estimated_ebitda,
                "ltm_ebit": estimated_ebitda * 0.85,  # Assume D&A is 15% of EBITDA
                "net_debt": estimated_ebitda * 0.5,  # Conservative net debt assumption
                "total_debt": estimated_ebitda * 1.0,
                "cash_and_equivalents": estimated_ebitda * 0.5,
                "capex": estimated_ebitda * 0.15,
                "depreciation_amortization": estimated_ebitda * 0.15,
                "interest_expense": estimated_ebitda * 0.02,
                "effective_tax_rate": 21.0  # US corporate rate
            })
        
        # Add default enterprise multiple if not available from ratios
        if "current_enterprise_multiple" not in result:
            # Use market cap / EBITDA as proxy for enterprise multiple
            if result.get("market_cap") and result.get("ltm_ebitda"):
                estimated_ev_multiple = (result["market_cap"] / 1_000_000) / result["ltm_ebitda"]
                result["current_enterprise_multiple"] = estimated_ev_multiple
                logger.info(f"Estimated enterprise multiple for {symbol}: {estimated_ev_multiple:.1f}x")
            else:
                # Fallback to reasonable default for large-cap stocks
                result["current_enterprise_multiple"] = 20.0
                logger.info(f"Using default enterprise multiple for {symbol}: 20.0x")
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting comprehensive financial data for {symbol}: {e}")
        raise 

async def get_enterprise_multiples(symbol: str) -> Dict[str, Any]:
    """Get enterprise multiples and key ratios from Financial Modeling Prep ratios API."""
    url = f"{FMP_BASE_URL}/ratios?symbol={symbol}&apikey={FMP_API_KEY}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and len(data) > 0:
                        # Get the most recent year's ratios (first item)
                        ratios = data[0]
                        return {
                            "symbol": ratios.get("symbol"),
                            "date": ratios.get("date"),
                            "fiscal_year": ratios.get("fiscalYear"),
                            "enterprise_value_multiple": ratios.get("enterpriseValueMultiple"),
                            "price_to_earnings_ratio": ratios.get("priceToEarningsRatio"),
                            "price_to_book_ratio": ratios.get("priceToBookRatio"),
                            "price_to_sales_ratio": ratios.get("priceToSalesRatio"),
                            "ebitda_margin": ratios.get("ebitdaMargin"),
                            "debt_to_equity_ratio": ratios.get("debtToEquityRatio"),
                            "current_ratio": ratios.get("currentRatio")
                        }
                    else:
                        logger.error(f"No ratio data found for {symbol}")
                        return None
                else:
                    logger.error(f"FMP ratios API error for {symbol}: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Error fetching ratios for {symbol}: {e}")
        return None 