from fastapi import FastAPI, HTTPException, Depends, Path, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional
import os
import json
import hashlib
import logging
from datetime import datetime
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession

# Import our modules
from models import get_async_session, Company, LBOOverride, LBODefaults, AsyncSessionLocal
from schemas import LBOResponse, LBOPatchRequest
from services.lbo_engine import run_lbo
from defaults import LBO_ASSUMPTIONS
import redis.asyncio as redis

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration
DB_HOST = os.getenv("DB_HOST", "orbe360.ai")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Admin0rbE")
DB_NAME = os.getenv("DB_NAME", "finmetrics")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_TTL = 120  # 2 minutes

app = FastAPI(
    title="LBO Analysis API",
    description="API for Leveraged Buyout financial modeling and analysis",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis client
redis_client = None

@app.on_event("startup")
async def startup_event():
    """Initialize Redis connection on startup."""
    global redis_client
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()
        logger.info("Redis connection established")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}. Caching will be disabled.")
        redis_client = None

@app.on_event("shutdown")
async def shutdown_event():
    """Close Redis connection on shutdown."""
    global redis_client
    if redis_client:
        await redis_client.close()

async def get_redis_client():
    """Dependency to get Redis client."""
    return redis_client

def generate_cache_key(ticker: str, overrides: Dict[str, Any]) -> str:
    """Generate cache key based on ticker and overrides hash."""
    overrides_str = json.dumps(overrides, sort_keys=True)
    overrides_hash = hashlib.md5(overrides_str.encode()).hexdigest()
    return f"lbo:{ticker.upper()}:{overrides_hash}"

async def get_cached_result(cache_key: str) -> Optional[Dict[str, Any]]:
    """Get cached LBO result."""
    if not redis_client:
        return None
    
    try:
        cached_data = await redis_client.get(cache_key)
        if cached_data:
            return json.loads(cached_data)
    except Exception as e:
        logger.warning(f"Cache read error: {e}")
    
    return None

async def set_cached_result(cache_key: str, result: Dict[str, Any]) -> None:
    """Cache LBO result."""
    if not redis_client:
        return
    
    try:
        await redis_client.setex(
            cache_key, 
            CACHE_TTL, 
            json.dumps(result, default=str)
        )
    except Exception as e:
        logger.warning(f"Cache write error: {e}")

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for database and network errors."""
    if "connection" in str(exc).lower() or "database" in str(exc).lower():
        return JSONResponse(
            status_code=503,
            content={"detail": "db_unavailable"}
        )
    
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

@app.get("/", tags=["Info"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": "LBO Analysis API",
        "version": "1.0.0",
        "description": "API for Leveraged Buyout financial modeling and analysis",
        "endpoints": {
            "POST /api/v1/lbo/{ticker}": "Run full LBO analysis",
            "PATCH /api/v1/lbo/{ticker}": "Update assumptions and recalculate",
            "GET /health": "Health check"
        }
    }

@app.get("/health", tags=["Info"])
async def health_check():
    """Health check endpoint."""
    try:
        # Test database connection
        async with AsyncSessionLocal() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        
        # Test Redis connection
        redis_status = "connected" if redis_client else "disabled"
        if redis_client:
            try:
                await redis_client.ping()
            except:
                redis_status = "error"
        
        return {
            "status": "healthy",
            "database": "connected",
            "redis": redis_status,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

@app.post("/api/v1/lbo/{ticker}", response_model=LBOResponse, tags=["LBO Analysis"])
async def run_lbo_analysis(
    ticker: str = Path(..., description="Company ticker symbol or identifier"),
    is_private: bool = False,
    session: AsyncSession = Depends(get_async_session)
):
    """
    Run full LBO analysis for a given ticker or private company.
    
    For public companies: Uses market data from financial_metrics table
    For private companies: Uses default assumptions (set is_private=True)
    
    Returns complete LBO model with purchase price, assumptions, sources & uses,
    pro forma cap table, returns analysis, IRR sensitivity, and financial projections.
    """
    ticker = ticker.upper()
    
    try:
        # Check cache first (include is_private in cache key)
        cache_key = generate_cache_key(f"{ticker}_private_{is_private}", {})
        cached_result = await get_cached_result(cache_key)
        if cached_result:
            logger.info(f"Returning cached result for {ticker} (private={is_private})")
            return cached_result
        
        # For private companies, skip database lookup
        if not is_private:
            # Verify ticker exists for public companies
            from sqlalchemy import text
            result = await session.execute(
                text("SELECT DISTINCT symbol FROM financial_metrics WHERE symbol = :ticker LIMIT 1"),
                {"ticker": ticker}
            )
            company_record = result.fetchone()
            
            if not company_record:
                raise HTTPException(
                    status_code=404,
                    detail=f"No financial data found for ticker {ticker}"
                )
        
        # Run LBO analysis with no overrides
        lbo_result = await run_lbo(ticker, {}, session, is_private)
        
        # Check if LBO analysis returned an error (e.g., negative EBITDA company)
        if isinstance(lbo_result, dict) and lbo_result.get("error") == "UNSUITABLE_FOR_LBO":
            raise HTTPException(
                status_code=400,
                detail={
                    "error_type": "UNSUITABLE_FOR_LBO",
                    "message": lbo_result["message"],
                    "explanation": lbo_result["explanation"],
                    "recommendation": lbo_result["recommendation"],
                    "company_metrics": {
                        "ticker": lbo_result["ticker"],
                        "ltm_ebitda": lbo_result["ltm_ebitda"],
                        "ltm_sales": lbo_result["ltm_sales"]
                    }
                }
            )
        
        # Cache the result
        await set_cached_result(cache_key, lbo_result)
        
        return lbo_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running LBO analysis for {ticker}: {e}")
        if "connection" in str(e).lower() or "database" in str(e).lower():
            raise HTTPException(status_code=503, detail="db_unavailable")
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/v1/lbo/{ticker}", response_model=LBOResponse, tags=["LBO Analysis"])
async def update_lbo_assumptions(
    patch_data: LBOPatchRequest,
    ticker: str = Path(..., description="Company ticker symbol or identifier"),
    is_private: bool = False,
    session: AsyncSession = Depends(get_async_session)
):
    """
    Update LBO assumptions and recalculate the model.
    
    For public companies: Updates assumptions based on market data
    For private companies: Updates assumptions and/or financial data (set is_private=True)
    
    Accepts partial updates to any field in the LBO model. Unknown keys return 400 Bad Request.
    Overrides are persisted in the lbo_override table for future reference.
    """
    ticker = ticker.upper()
    
    try:
        # Validate patch data against known schema
        overrides = patch_data.model_dump(exclude_unset=True)
        
        if not overrides:
            raise HTTPException(
                status_code=400,
                detail="No valid override fields provided"
            )
        
        # Check cache with overrides (include is_private in cache key)
        cache_key = generate_cache_key(f"{ticker}_private_{is_private}", overrides)
        cached_result = await get_cached_result(cache_key)
        if cached_result:
            logger.info(f"Returning cached result for {ticker} with overrides (private={is_private})")
            return cached_result
        
        # For private companies, skip database lookup
        if not is_private:
            # Verify ticker exists for public companies
            from sqlalchemy import text
            result = await session.execute(
                text("SELECT DISTINCT symbol FROM financial_metrics WHERE symbol = :ticker LIMIT 1"),
                {"ticker": ticker}
            )
            company_record = result.fetchone()
            
            if not company_record:
                raise HTTPException(
                    status_code=404,
                    detail=f"No financial data found for ticker {ticker}"
                )
        
        # Save overrides to database (simplified - using ticker as company_id for now)
        # In production, you'd want proper user authentication and company_id lookup
        try:
            override_record = LBOOverride(
                company_id=ticker,  # Using ticker as ID for simplicity
                user_id="system",   # Would be actual user ID in production
                overrides_json=overrides,
                created_at=datetime.utcnow()
            )
            session.add(override_record)
            await session.commit()
        except Exception as e:
            logger.warning(f"Could not save overrides to database: {e}")
            # Continue without saving overrides - this is optional functionality
        
        # Run LBO analysis with overrides
        lbo_result = await run_lbo(ticker, overrides, session, is_private)
        
        # Check if LBO analysis returned an error (e.g., negative EBITDA company)
        if isinstance(lbo_result, dict) and lbo_result.get("error") == "UNSUITABLE_FOR_LBO":
            raise HTTPException(
                status_code=400,
                detail={
                    "error_type": "UNSUITABLE_FOR_LBO",
                    "message": lbo_result["message"],
                    "explanation": lbo_result["explanation"],
                    "recommendation": lbo_result["recommendation"],
                    "company_metrics": {
                        "ticker": lbo_result["ticker"],
                        "ltm_ebitda": lbo_result["ltm_ebitda"],
                        "ltm_sales": lbo_result["ltm_sales"]
                    },
                    "override_hint": "To force analysis on unprofitable companies, add 'allow_negative_ebitda': true to your request"
                }
            )
        
        # Cache the result
        await set_cached_result(cache_key, lbo_result)
        
        return lbo_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating LBO assumptions for {ticker}: {e}")
        if "connection" in str(e).lower() or "database" in str(e).lower():
            raise HTTPException(status_code=503, detail="db_unavailable")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 