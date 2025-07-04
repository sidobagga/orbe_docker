from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

class PurchasePrice(BaseModel):
    # UNIFIED STRUCTURE: All fields now available for both public and private companies
    # For private companies, share-related fields represent "units" where 1 unit = $1M equity value
    basicShares: float = Field(..., description="Basic shares outstanding (millions) or equity units for private companies")
    currentPricePerShare: float = Field(..., description="Current share price or equity value per unit")
    impliedPricePerShare: float = Field(..., description="Implied price per share/unit based on EBITDA valuation")
    offerPremiumPct: float = Field(..., description="Offer premium percentage")
    offerPricePerShare: float = Field(..., description="Offer price per share/unit")
    fullyDilutedShares: float = Field(..., description="Fully diluted shares (millions) or equity units")
    
    # Universal fields (required for both public and private)
    equityOfferPrice: float = Field(..., description="Total equity offer price (millions)")
    enterpriseValue: float = Field(..., description="Enterprise value (millions)")
    entryMultiple: float = Field(..., description="Entry EBITDA multiple used")
    currentTradingMultiple: Optional[float] = Field(None, description="Current market EV/EBITDA multiple (N/A for private)")
    note: Optional[str] = Field(None, description="Notes about valuation methodology")
    
    # Private company specific fields (kept for backward compatibility)
    equityValue: Optional[float] = Field(None, description="Raw equity value for private companies (millions)")
    underwaterEquity: Optional[bool] = Field(None, description="Flag indicating if equity is underwater at entry")

class Assumptions(BaseModel):
    baseYear: int = Field(..., description="Base year for analysis")
    entryMultiple: float = Field(..., description="Entry EBITDA multiple")
    exitMultiple: float = Field(..., description="Exit EBITDA multiple")
    sponsorTargetIRR: float = Field(..., description="Target IRR for sponsor")
    transactionFeesPct: float = Field(..., description="Transaction fees percentage")
    cashToBalanceSheet: float = Field(..., description="Cash to balance sheet (millions)")
    taxRatePct: float = Field(..., description="Tax rate percentage")

class SourcesUsesItem(BaseModel):
    label: str = Field(..., description="Source or use description")
    amount: float = Field(..., description="Amount in millions")

class SourcesAndUses(BaseModel):
    sources: List[SourcesUsesItem] = Field(..., description="Sources of funds")
    uses: List[SourcesUsesItem] = Field(..., description="Uses of funds")
    totalSources: float = Field(..., description="Total sources (millions)")
    totalUses: float = Field(..., description="Total uses (millions)")

class DebtTranche(BaseModel):
    amount: float = Field(..., description="Debt amount (millions)")
    pctOfCapital: float = Field(..., description="Percentage of total capital")
    cumulativeMultipleOfEBITDA: float = Field(..., description="Multiple of EBITDA")

class SponsorEquity(BaseModel):
    amount: float = Field(..., description="Sponsor equity amount (millions)")
    pctOfCapital: float = Field(..., description="Percentage of total capital")

class ProFormaCapTable(BaseModel):
    cash: float = Field(..., description="Cash on balance sheet (millions)")
    firstLienTermLoan: Dict[str, float] = Field(..., description="First lien term loan details")
    secondLien: Dict[str, float] = Field(..., description="Second lien details")
    mezzanine: Dict[str, float] = Field(..., description="Mezzanine financing details (always included)")
    sponsorEquity: Dict[str, float] = Field(..., description="Sponsor equity details")
    totalCapitalization: float = Field(..., description="Total capitalization (millions)")
    ltmUnleveredEBITDA: float = Field(..., description="LTM unlevered EBITDA (millions)")

class ReturnsAnalysis(BaseModel):
    terminalEBITDA: float = Field(..., description="Terminal EBITDA (millions)")
    exitMultiple: float = Field(..., description="Exit multiple")
    enterpriseValue: float = Field(..., description="Enterprise value at exit (millions)")
    lessNetDebt: float = Field(..., description="Net debt at exit (millions)")
    equityValueAtExit: float = Field(..., description="Equity value at exit (millions)")
    sponsorOwnershipPctAtExit: float = Field(..., description="Sponsor ownership at exit")
    sponsorEquityValueAtExit: float = Field(..., description="Sponsor equity value at exit (millions)")
    sponsorEquityValueAtClosing: float = Field(..., description="Sponsor equity value at closing (millions)")
    IRR: float = Field(..., description="Internal rate of return")

class IRRSensitivityCell(BaseModel):
    # UNIFIED STRUCTURE: Both fields now always included for consistency
    equityValuePerShare: float = Field(..., description="Required equity value per share/unit at closing to meet hurdle IRR")
    totalEquityValue: float = Field(..., description="Total equity value at exit (millions)")
    # Universal fields
    impliedNetDebt: float = Field(..., description="Net debt at exit (millions)")
    enterpriseValue: float = Field(..., description="Enterprise value at exit (millions)")
    requiredEquityAtClosing: float = Field(..., description="Required total equity at closing to meet hurdle IRR (millions)")

class IRRSensitivityAssumptions(BaseModel):
    holdPeriod: int = Field(..., description="Investment hold period in years")
    sponsorOwnershipPct: float = Field(..., description="Sponsor ownership percentage")
    terminalEBITDA: float = Field(..., description="Terminal EBITDA (millions)")
    sponsorEquityAtClosing: float = Field(..., description="Sponsor equity at closing (millions)")
    fullyDilutedShares: float = Field(..., description="Fully diluted shares/units outstanding (millions)")

class IRRSensitivity(BaseModel):
    sponsorRequiredIRRs: List[float] = Field(..., description="Sponsor required IRR percentages (Y-axis)")
    exitMultiples: List[float] = Field(..., description="Exit multiples for sensitivity (X-axis)")
    matrix: List[List[IRRSensitivityCell]] = Field(..., description="Matrix of equity values to meet hurdle IRRs")
    assumptions: IRRSensitivityAssumptions = Field(..., description="Key assumptions used in sensitivity analysis")
    note: str = Field(..., description="Description of what the matrix shows")

class FreeCashFlow(BaseModel):
    ebitda: float = Field(..., description="EBITDA (millions)")
    lessCapex: float = Field(..., description="Less capex (millions)")
    lessIncreaseInNWC: float = Field(..., description="Less increase in NWC (millions)")
    lessCashInterest: float = Field(..., description="Less cash interest (millions)")
    lessCashTaxes: float = Field(..., description="Less cash taxes (millions)")
    fCFForDebtRepayment: float = Field(..., description="FCF for debt repayment (millions)")

class FinancialProjection(BaseModel):
    year: int = Field(..., description="Projection year")
    sales: float = Field(..., description="Sales (millions)")
    salesGrowthPct: Optional[float] = Field(None, description="Sales growth percentage")
    ebitda: float = Field(..., description="EBITDA (millions)")
    ebitdaMarginPct: Optional[float] = Field(None, description="EBITDA margin percentage")
    ebit: float = Field(..., description="EBIT (millions)")
    ebitMarginPct: Optional[float] = Field(None, description="EBIT margin percentage")
    dAndA: float = Field(..., description="Depreciation and amortization (millions)")
    dAndAAsPctOfSales: Optional[float] = Field(None, description="D&A as percentage of sales")
    capex: float = Field(..., description="Capital expenditure (millions)")
    capexAsPctOfSales: Optional[float] = Field(None, description="Capex as percentage of sales")
    netWorkingCapital: float = Field(..., description="Net working capital (millions)")
    nwcAsPctOfSales: Optional[float] = Field(None, description="NWC as percentage of sales")
    freeCashFlow: FreeCashFlow = Field(..., description="Free cash flow breakdown")

class LBOResponse(BaseModel):
    """Complete LBO analysis response matching the exact JSON contract."""
    purchasePrice: PurchasePrice = Field(..., description="Purchase price details")
    assumptions: Assumptions = Field(..., description="LBO assumptions")
    sourcesAndUses: SourcesAndUses = Field(..., description="Sources and uses of funds")
    proFormaCapTable: ProFormaCapTable = Field(..., description="Pro forma capitalization table")
    returnsAnalysis: ReturnsAnalysis = Field(..., description="Returns analysis")
    irrSensitivity: IRRSensitivity = Field(..., description="IRR sensitivity analysis")
    financialProjections: List[FinancialProjection] = Field(..., description="Financial projections")
    
    # Optional field for private companies
    defaultsApplied: Optional[List[str]] = Field(None, description="List of fields that used default values (private companies)")

# PATCH request schemas - all fields optional for partial updates
class PurchasePricePatch(BaseModel):
    basicShares: Optional[float] = None
    currentPricePerShare: Optional[float] = None
    impliedPricePerShare: Optional[float] = None
    offerPremiumPct: Optional[float] = None
    offerPricePerShare: Optional[float] = None
    fullyDilutedShares: Optional[float] = None
    equityOfferPrice: Optional[float] = None
    enterpriseValue: Optional[float] = None
    entryMultiple: Optional[float] = None
    currentTradingMultiple: Optional[float] = None
    note: Optional[str] = None

class AssumptionsPatch(BaseModel):
    baseYear: Optional[int] = None
    entryMultiple: Optional[float] = None
    exitMultiple: Optional[float] = None
    sponsorTargetIRR: Optional[float] = None
    transactionFeesPct: Optional[float] = None
    cashToBalanceSheet: Optional[float] = None
    taxRatePct: Optional[float] = None

class SourcesUsesItemPatch(BaseModel):
    label: Optional[str] = None
    amount: Optional[float] = None

class SourcesAndUsesPatch(BaseModel):
    sources: Optional[List[SourcesUsesItemPatch]] = None
    uses: Optional[List[SourcesUsesItemPatch]] = None
    totalSources: Optional[float] = None
    totalUses: Optional[float] = None

class DebtTranchePatch(BaseModel):
    amount: Optional[float] = None
    pctOfCapital: Optional[float] = None
    cumulativeMultipleOfEBITDA: Optional[float] = None

class SponsorEquityPatch(BaseModel):
    amount: Optional[float] = None
    pctOfCapital: Optional[float] = None

class ProFormaCapTablePatch(BaseModel):
    cash: Optional[float] = None
    firstLienTermLoan: Optional[DebtTranchePatch] = None
    secondLien: Optional[DebtTranchePatch] = None
    mezzanine: Optional[DebtTranchePatch] = None
    sponsorEquity: Optional[SponsorEquityPatch] = None
    totalCapitalization: Optional[float] = None
    ltmUnleveredEBITDA: Optional[float] = None

class ReturnsAnalysisPatch(BaseModel):
    terminalEBITDA: Optional[float] = None
    exitMultiple: Optional[float] = None
    enterpriseValue: Optional[float] = None
    lessNetDebt: Optional[float] = None
    equityValueAtExit: Optional[float] = None
    sponsorOwnershipPctAtExit: Optional[float] = None
    sponsorEquityValueAtExit: Optional[float] = None
    sponsorEquityValueAtClosing: Optional[float] = None
    IRR: Optional[float] = None

class IRRSensitivityPatch(BaseModel):
    sponsorRequiredIRRs: Optional[List[float]] = None
    exitMultiples: Optional[List[float]] = None
    matrix: Optional[List[List[IRRSensitivityCell]]] = None
    assumptions: Optional[IRRSensitivityAssumptions] = None
    note: Optional[str] = None

class FreeCashFlowPatch(BaseModel):
    ebitda: Optional[float] = None
    lessCapex: Optional[float] = None
    lessIncreaseInNWC: Optional[float] = None
    lessCashInterest: Optional[float] = None
    lessCashTaxes: Optional[float] = None
    fCFForDebtRepayment: Optional[float] = None

class FinancialProjectionPatch(BaseModel):
    year: Optional[int] = None
    sales: Optional[float] = None
    salesGrowthPct: Optional[float] = None
    ebitda: Optional[float] = None
    ebitdaMarginPct: Optional[float] = None
    ebit: Optional[float] = None
    ebitMarginPct: Optional[float] = None
    dAndA: Optional[float] = None
    dAndAAsPctOfSales: Optional[float] = None
    capex: Optional[float] = None
    capexAsPctOfSales: Optional[float] = None
    netWorkingCapital: Optional[float] = None
    nwcAsPctOfSales: Optional[float] = None
    freeCashFlow: Optional[FreeCashFlowPatch] = None

class LBOPatchRequest(BaseModel):
    """PATCH request schema for updating LBO assumptions."""
    purchasePrice: Optional[PurchasePricePatch] = None
    assumptions: Optional[AssumptionsPatch] = None
    sourcesAndUses: Optional[SourcesAndUsesPatch] = None
    proFormaCapTable: Optional[ProFormaCapTablePatch] = None
    returnsAnalysis: Optional[ReturnsAnalysisPatch] = None
    irrSensitivity: Optional[IRRSensitivityPatch] = None
    financialProjections: Optional[List[FinancialProjectionPatch]] = None
    
    # Private company financial data fields
    ltm_ebitda: Optional[float] = Field(None, description="LTM EBITDA for private companies (millions)")
    ltm_sales: Optional[float] = Field(None, description="LTM Sales for private companies (millions)")
    net_debt: Optional[float] = Field(None, description="Net debt for private companies (millions)")

    class Config:
        extra = "forbid"  # Reject unknown fields with 400 Bad Request 