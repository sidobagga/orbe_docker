-- Initialize database for LBO API
-- This script runs when the PostgreSQL container starts

-- Create finmetrics database if it doesn't exist
SELECT 'CREATE DATABASE finmetrics'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'finmetrics');

-- Connect to finmetrics database
\c finmetrics;

-- Create extensions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Basic health check
SELECT 'Database initialized successfully' as status;