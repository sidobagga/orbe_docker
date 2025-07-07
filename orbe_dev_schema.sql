-- =====================================================
-- ORBE_DEV DATABASE SCHEMA
-- =====================================================
-- Complete database schema for orbe_dev PostgreSQL database
-- Generated from: orbe360.ai:5432/orbe_dev
-- =====================================================

-- =====================================================
-- ENUM TYPES
-- =====================================================

-- Companies role enumeration
CREATE TYPE companies_role_enum AS ENUM ('admin', 'investor', 'startup');

-- Company type enumeration  
CREATE TYPE company_type_enum AS ENUM ('public', 'private');

-- Deals status enumeration
CREATE TYPE deals_status_enum AS ENUM ('archived', 'deleted', 'active');

-- Insights status enumeration
CREATE TYPE insights_status_enum AS ENUM ('pending', 'complete');

-- User status enumeration
CREATE TYPE user_status_enum AS ENUM ('active', 'inactive');

-- =====================================================
-- TABLES
-- =====================================================

-- =====================================================
-- 1. COMPANIES TABLE
-- =====================================================
CREATE TABLE companies (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    name character varying NOT NULL,
    role companies_role_enum NOT NULL,
    createdAt timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedAt timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sectors text[],
    planType character varying DEFAULT 'TRIAL'::character varying,
    subscriptionStartDate timestamp without time zone,
    subscriptionEndDate timestamp without time zone,
    discountPercentage double precision,
    myInvestmentThesis text,
    investmentFocus text,
    tags jsonb NOT NULL DEFAULT '[{"label": "B2B", "value": "b2b", "category": "Business Model"}, {"label": "B2C", "value": "b2c", "category": "Business Model"}, {"label": "Marketplace", "value": "marketplace", "category": "Business Model"}, {"label": "Platform Play", "value": "platform_play", "category": "Thesis Fit"}, {"label": "ESG", "value": "esg", "category": "Thesis Fit"}, {"label": "Disruptive Tech", "value": "disruptive_tech", "category": "Thesis Fit"}, {"label": "IPO Candidate", "value": "ipo_candidate", "category": "Exit Potential"}, {"label": "M&A Target", "value": "mna_target", "category": "Exit Potential"}, {"label": "Strategic Acquisition", "value": "strategic_acquisition", "category": "Exit Potential"}, {"label": "Revenue Generating", "value": "revenue_generating", "category": "Traction"}, {"label": "Hypergrowth", "value": "hypergrowth", "category": "Traction"}, {"label": "Profitable", "value": "profitable", "category": "Traction"}, {"label": "Repeat Founder", "value": "repeat_founder", "category": "Founder/Team"}, {"label": "Technical Founder", "value": "technical_founder", "category": "Founder/Team"}, {"label": "Diverse Team", "value": "diverse_team", "category": "Founder/Team"}]'::jsonb
);

-- =====================================================
-- 2. USERS TABLE
-- =====================================================
CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    firstName character varying NOT NULL,
    lastName character varying NOT NULL,
    email character varying NOT NULL UNIQUE,
    password character varying NOT NULL,
    verificationToken character varying,
    verificationTokenExpiry timestamp without time zone,
    isVerified boolean NOT NULL DEFAULT false,
    createdAt timestamp without time zone NOT NULL DEFAULT now(),
    updatedAt timestamp without time zone NOT NULL DEFAULT now(),
    refreshToken character varying,
    companyId uuid,
    status user_status_enum NOT NULL DEFAULT 'active'::user_status_enum,
    FOREIGN KEY (companyId) REFERENCES companies(id) ON DELETE SET NULL
);

-- =====================================================
-- 3. PUBLIC MARKETS TABLE
-- =====================================================
CREATE TABLE public_markets (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol character varying NOT NULL UNIQUE,
    companyOverview jsonb,
    pressReleases jsonb,
    createdAt timestamp with time zone NOT NULL DEFAULT now(),
    updatedAt timestamp with time zone NOT NULL DEFAULT now(),
    companyProfile jsonb
);

-- =====================================================
-- 4. COMPANY MARKETS TABLE (Junction)
-- =====================================================
CREATE TABLE company_markets (
    companyId uuid NOT NULL,
    marketId uuid NOT NULL,
    createdAt timestamp with time zone NOT NULL DEFAULT now(),
    updatedAt timestamp with time zone NOT NULL DEFAULT now(),
    PRIMARY KEY (companyId, marketId),
    FOREIGN KEY (companyId) REFERENCES companies(id) ON DELETE CASCADE,
    FOREIGN KEY (marketId) REFERENCES public_markets(id) ON DELETE CASCADE
);

-- =====================================================
-- 5. COMPANY REPORT TABLE
-- =====================================================
CREATE TABLE company_report (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticker character varying NOT NULL,
    companyName character varying NOT NULL,
    reportData jsonb NOT NULL,
    filingType character varying,
    createdAt timestamp without time zone NOT NULL DEFAULT now(),
    updatedAt timestamp without time zone NOT NULL DEFAULT now(),
    insights jsonb,
    products jsonb,
    markets jsonb
);

-- Index for company_report
CREATE INDEX IDX_COMPANY_REPORT_TICKER ON company_report(ticker);

-- =====================================================
-- 6. DATA ROOMS TABLE
-- =====================================================
CREATE TABLE data_rooms (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    documentType character varying NOT NULL,
    document text NOT NULL,
    companyId uuid NOT NULL,
    createdAt timestamp without time zone NOT NULL DEFAULT now(),
    updatedAt timestamp without time zone NOT NULL DEFAULT now(),
    name text,
    extractedText text,
    FOREIGN KEY (companyId) REFERENCES companies(id) ON DELETE CASCADE
);

-- =====================================================
-- 7. DEALS TABLE
-- =====================================================
CREATE TABLE deals (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    investorId uuid NOT NULL,
    startupEmail character varying NOT NULL,
    startupId character varying,
    createdAt timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedAt timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    pitchDeck jsonb,
    isFavorite boolean NOT NULL DEFAULT false,
    status deals_status_enum NOT NULL DEFAULT 'active'::deals_status_enum,
    pitchDeckForm jsonb,
    investorEmail character varying NOT NULL DEFAULT ''::character varying,
    insightsStatus insights_status_enum NOT NULL DEFAULT 'pending'::insights_status_enum,
    tags jsonb NOT NULL DEFAULT '[]'::jsonb,
    FOREIGN KEY (investorId) REFERENCES companies(id) ON DELETE CASCADE
);

-- =====================================================
-- 8. INSIGHTS TABLE
-- =====================================================
CREATE TABLE insights (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    dealId uuid NOT NULL UNIQUE,
    profile jsonb NOT NULL,
    market jsonb NOT NULL,
    product jsonb NOT NULL,
    pitchDeckSentiment jsonb NOT NULL,
    companySentiment jsonb NOT NULL,
    founderSentiment jsonb NOT NULL,
    createdAt timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedAt timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    financial jsonb DEFAULT '{}'::jsonb,
    investmentMemo jsonb,
    investments jsonb,
    FOREIGN KEY (dealId) REFERENCES deals(id) ON DELETE CASCADE
);

-- =====================================================
-- 9. EARNINGS TRANSCRIPT TABLE
-- =====================================================
CREATE TABLE earnings_transcript (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    company character varying NOT NULL,
    year integer NOT NULL,
    quarter integer NOT NULL,
    transcript text NOT NULL,
    positive text,
    negative text,
    neutral text,
    summary text NOT NULL,
    terms jsonb,
    positive_count integer,
    negative_count integer,
    neutral_count integer,
    date character varying,
    updatedAt timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- 10. NEWS TABLE
-- =====================================================
CREATE TABLE news (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    title character varying NOT NULL,
    description text NOT NULL,
    url character varying NOT NULL,
    sector character varying NOT NULL,
    datePublished character varying NOT NULL,
    createdAt timestamp without time zone NOT NULL DEFAULT now(),
    updatedAt timestamp without time zone NOT NULL DEFAULT now()
);

-- Index for news
CREATE INDEX IDX_NEWS_SECTOR ON news(sector);

-- =====================================================
-- 11. NOTES TABLE
-- =====================================================
CREATE TABLE notes (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    title character varying NOT NULL,
    content text,
    extractedContent text,
    synthesizedContent jsonb,
    companyId uuid,
    createdAt timestamp without time zone NOT NULL DEFAULT now(),
    updatedAt timestamp without time zone NOT NULL DEFAULT now(),
    files text[],
    FOREIGN KEY (companyId) REFERENCES companies(id) ON DELETE CASCADE
);

-- Index for notes
CREATE INDEX IDX_notes_companyId ON notes(companyId);

-- =====================================================
-- 12. OTPS TABLE
-- =====================================================
CREATE TABLE otps (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    code character varying NOT NULL,
    expiresAt timestamp without time zone NOT NULL,
    userId uuid NOT NULL UNIQUE,
    createdAt timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedAt timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (userId) REFERENCES users(id) ON DELETE CASCADE
);

-- =====================================================
-- 13. PE COMPANIES TABLE
-- =====================================================
CREATE TABLE pe_companies (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    companyId character varying NOT NULL,
    companyName character varying NOT NULL,
    companyType company_type_enum NOT NULL,
    industry character varying,
    websiteUrl character varying,
    createdAt timestamp without time zone NOT NULL DEFAULT now(),
    updatedAt timestamp without time zone NOT NULL DEFAULT now()
);

-- =====================================================
-- 14. PE COMPANY MARKETS TABLE
-- =====================================================
CREATE TABLE pe_company_markets (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    companyId uuid NOT NULL,
    peCompanyId uuid NOT NULL,
    createdAt timestamp without time zone NOT NULL DEFAULT now(),
    updatedAt timestamp without time zone NOT NULL DEFAULT now(),
    FOREIGN KEY (companyId) REFERENCES companies(id) ON DELETE CASCADE,
    FOREIGN KEY (peCompanyId) REFERENCES pe_companies(id) ON DELETE CASCADE
);

-- =====================================================
-- 15. PE DATAROOM TABLE
-- =====================================================
CREATE TABLE pe_dataroom (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    documentType character varying NOT NULL,
    document character varying NOT NULL,
    companyId uuid NOT NULL,
    createdAt timestamp without time zone NOT NULL DEFAULT now(),
    updatedAt timestamp without time zone NOT NULL DEFAULT now(),
    extractedText jsonb,
    FOREIGN KEY (companyId) REFERENCES pe_companies(id) ON DELETE SET NULL
);

-- =====================================================
-- 16. PE LBO ANALYSIS TABLE
-- =====================================================
CREATE TABLE pe_lbo_analysis (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    userId uuid NOT NULL,
    companyId uuid,
    lboData jsonb NOT NULL,
    FOREIGN KEY (userId) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (companyId) REFERENCES pe_companies(id) ON DELETE SET NULL
);

-- =====================================================
-- 17. PE SECTIONS DATA TABLE
-- =====================================================
CREATE TABLE pe_sections_data (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    companyId uuid NOT NULL,
    companyProfile jsonb NOT NULL,
    markets jsonb NOT NULL,
    products jsonb NOT NULL,
    createdAt timestamp without time zone NOT NULL DEFAULT now(),
    updatedAt timestamp without time zone NOT NULL DEFAULT now(),
    FOREIGN KEY (companyId) REFERENCES pe_companies(id) ON DELETE CASCADE
);

-- =====================================================
-- 18. MIGRATIONS TABLE
-- =====================================================
CREATE TABLE migrations (
    id serial PRIMARY KEY,
    timestamp bigint NOT NULL,
    name character varying NOT NULL
);

-- =====================================================
-- KEY RELATIONSHIPS SUMMARY
-- =====================================================
-- 
-- Primary Relationships:
-- • companies (1:N) → users (via companyId)
-- • companies (1:N) → deals (via investorId)
-- • companies (1:N) → data_rooms (via companyId)
-- • companies (1:N) → notes (via companyId)
-- • companies (M:N) → public_markets (via company_markets junction table)
-- • deals (1:1) → insights (via dealId)
-- • users (1:1) → otps (via userId)
-- • users (1:N) → pe_lbo_analysis (via userId)
-- • pe_companies (1:N) → pe_dataroom (via companyId)
-- • pe_companies (1:N) → pe_lbo_analysis (via companyId)
-- • pe_companies (1:N) → pe_sections_data (via companyId)
-- • pe_companies (M:N) → companies (via pe_company_markets junction table)
-- 
-- Key Features:
-- • UUID primary keys for all main entities
-- • JSONB columns for flexible data storage
-- • Proper foreign key constraints with CASCADE/SET NULL policies
-- • Timestamp tracking (createdAt/updatedAt)
-- • Enum types for controlled vocabulary
-- • Indexes on frequently queried columns
-- 
-- ===================================================== 