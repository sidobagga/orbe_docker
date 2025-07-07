# Changelog

All notable changes to this project will be documented in this file.

## [v0.1.0-alpha] - 2025-07-06

### Added
- Initial Docker-based platform for financial analysis and LBO modeling
- Comprehensive microservices architecture with 10+ services
- PostgreSQL and Redis data layer with health checks
- AI-powered insights including market, sentiment, and financial analysis
- Text extraction services with OCR support for document processing
- Automated memo generation and interactive chatbot interface
- Environment variable management with .env.example template
- GitHub Actions CI/CD pipeline for automated building and testing
- Pre-commit hooks for code quality (Black, isort, Ruff, hadolint)
- Makefile with dev/test/prod targets for easy development
- Docker Compose override for local development with volume mounting
- Comprehensive README with architecture diagram and 30-second smoke test
- MIT License for open-source distribution

### Changed
- Moved from hardcoded credentials to environment variable management
- Updated Docker build contexts to use correct Dockerfile paths
- Improved .gitignore with comprehensive Python and Docker patterns

### Security
- Removed hardcoded database passwords from version control
- Implemented proper environment variable handling for sensitive data
- Added .env to .gitignore to prevent credential leakage

### Developer Experience
- Added make targets for common development tasks
- Implemented hot-reload capabilities for local development
- Added comprehensive health checks across all services
- Included automated testing in CI pipeline