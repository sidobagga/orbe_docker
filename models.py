from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from typing import AsyncGenerator

# Database configuration
DB_HOST = os.getenv("DB_HOST", "orbe360.ai")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Admin0rbE")
DB_NAME = os.getenv("DB_NAME", "finmetrics")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=False)

# Create async session factory
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

class Company(Base):
    """Company table - using existing financial_metrics table structure."""
    __tablename__ = "financial_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    date = Column(String)
    period = Column(String)
    reportedcurrency = Column(String)
    fiscalyear = Column(Integer)
    fiscalquarter = Column(Integer)
    data_source = Column(String)
    metric_type = Column(String)
    metric_values = Column(JSON)

class LBODefaults(Base):
    """LBO default assumptions table."""
    __tablename__ = "lbo_defaults"
    
    id = Column(Integer, primary_key=True, index=True)
    parameter_name = Column(String, unique=True, index=True)
    parameter_value = Column(Float)
    parameter_type = Column(String)  # 'float', 'percentage', 'array'
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class LBOOverride(Base):
    """LBO override table for storing user customizations."""
    __tablename__ = "lbo_override"
    
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(String, index=True)  # Using ticker as company_id for simplicity
    user_id = Column(String, index=True)
    overrides_json = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def create_tables():
    """Create all tables."""
    async with engine.begin() as conn:
        # Only create LBO-specific tables, not the existing financial_metrics table
        await conn.run_sync(Base.metadata.create_all)

async def init_default_values():
    """Initialize default LBO values in the database."""
    from defaults import DEFAULT_LBO_ASSUMPTIONS
    
    async with AsyncSessionLocal() as session:
        # Check if defaults already exist
        existing_defaults = await session.execute(
            "SELECT COUNT(*) FROM lbo_defaults"
        )
        count = existing_defaults.scalar()
        
        if count == 0:
            # Insert default values
            defaults_to_insert = [
                LBODefaults(
                    parameter_name="entry_multiple",
                    parameter_value=DEFAULT_LBO_ASSUMPTIONS["entryMultiple"],
                    parameter_type="float",
                    description="Entry EBITDA multiple for LBO"
                ),
                LBODefaults(
                    parameter_name="exit_multiple", 
                    parameter_value=DEFAULT_LBO_ASSUMPTIONS["exitMultiple"],
                    parameter_type="float",
                    description="Exit EBITDA multiple for LBO"
                ),
                LBODefaults(
                    parameter_name="tax_rate_pct",
                    parameter_value=DEFAULT_LBO_ASSUMPTIONS["taxRatePct"],
                    parameter_type="percentage",
                    description="Corporate tax rate percentage"
                ),
                LBODefaults(
                    parameter_name="sponsor_target_irr",
                    parameter_value=DEFAULT_LBO_ASSUMPTIONS["sponsorTargetIRR"],
                    parameter_type="percentage", 
                    description="Target IRR for sponsor"
                ),
                LBODefaults(
                    parameter_name="transaction_fees_pct",
                    parameter_value=DEFAULT_LBO_ASSUMPTIONS["transactionFeesPct"],
                    parameter_type="percentage",
                    description="Transaction fees as percentage of deal value"
                ),
                LBODefaults(
                    parameter_name="cash_to_balance_sheet",
                    parameter_value=DEFAULT_LBO_ASSUMPTIONS["cashToBalanceSheet"],
                    parameter_type="float",
                    description="Cash to maintain on balance sheet (millions)"
                ),
                LBODefaults(
                    parameter_name="offer_premium_pct",
                    parameter_value=DEFAULT_LBO_ASSUMPTIONS["offerPremiumPct"],
                    parameter_type="percentage",
                    description="Offer premium over current share price"
                )
            ]
            
            for default in defaults_to_insert:
                session.add(default)
            
            await session.commit()

if __name__ == "__main__":
    import asyncio
    
    async def main():
        await create_tables()
        await init_default_values()
        print("Database tables created and default values initialized.")
    
    asyncio.run(main()) 