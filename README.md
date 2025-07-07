# Orbe Financial Services Docker Platform

A comprehensive Docker-based platform for financial analysis, LBO modeling, and AI-powered insights.

## Services Overview

### Core Services
- **PostgreSQL Database** (Port 5432) - Primary data storage
- **Redis Cache** (Port 6379) - Caching layer
- **LBO API** (Port 8000) - Main financial API service
- **Unified API** (Port 8080) - Consolidated financial data API

### Text Processing Services
- **LBO Text Extraction** (Port 8061) - Document processing with OCR
- **VC Text Extraction** (Port 8060) - VC-specific document processing

### Analysis Services
- **LBO Analysis** (Port 8001) - LBO modeling and analysis
- **VC Analysis** (Port 8005) - Venture capital analysis

### AI Services
- **AI Insights** (Ports 8010, 8020, 8030, 8040) - Market, product, financial, and sentiment analysis
- **Sector News** (Port 8050) - Sector-specific news aggregation
- **Memo Generator** (Port 8070) - Automated memo generation
- **Chatbot** (Port 8090) - Interactive chat interface

## Prerequisites

- Docker and Docker Compose
- Required API keys (see Environment Variables section)

## Quick Start

1. **Clone and navigate to the project directory**
   ```bash
   cd docker_orbe
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Start all services**
   ```bash
   docker-compose up -d
   ```

4. **Check service health**
   ```bash
   docker-compose ps
   ```

## Environment Variables

Create a `.env` file with the following variables:

```env
# API Keys
FMP_API_KEY=your_fmp_api_key
OPENAI_API_KEY=your_openai_api_key
HUGGINGFACE_API_KEY=your_huggingface_api_key
PERPLEXITY_API_KEY=your_perplexity_api_key
GROQ_API_KEY=your_groq_api_key
```

## Service Details

### Database Services
- **PostgreSQL**: Stores financial data, user information, and analysis results
- **Redis**: Provides caching for improved performance

### Text Processing
- **OCR Support**: Enabled for document processing
- **File Size Limits**: 100MB maximum file size
- **Processing Timeout**: 120 seconds for downloads

### AI Analysis
- **Market Analysis**: Real-time market insights
- **Sentiment Analysis**: News and social media sentiment
- **Financial Modeling**: LBO and VC analysis capabilities
- **Document Processing**: Automated extraction and analysis

## Port Mapping

| Service | Port | Description |
|---------|------|-------------|
| PostgreSQL | 5432 | Database |
| Redis | 6379 | Cache |
| LBO API | 8000 | Main API |
| LBO Analysis | 8001 | LBO Analysis |
| VC Analysis | 8005 | VC Analysis |
| AI Market Insights | 8010 | Market Analysis |
| AI Product Insights | 8020 | Product Analysis |
| AI Financial Insights | 8030 | Financial Analysis |
| AI Sentiment Insights | 8040 | Sentiment Analysis |
| Sector News | 8050 | News Service |
| VC Text Extraction | 8060 | VC Document Processing |
| LBO Text Extraction | 8061 | LBO Document Processing |
| Memo Generator | 8070 | Memo Creation |
| Unified API | 8080 | Consolidated API |
| Chatbot | 8090 | Chat Interface |

## Development

### Individual Service Management
```bash
# Start specific services
docker-compose up -d postgres redis lbo-api

# View logs
docker-compose logs -f lbo-api

# Restart a service
docker-compose restart lbo-analysis

# Stop all services
docker-compose down
```

### Database Management
```bash
# Access PostgreSQL
docker exec -it lbo-postgres psql -U postgres -d finmetrics

# Access Redis
docker exec -it lbo-redis redis-cli
```

## Health Checks

All services include health checks. Monitor service status:
```bash
docker-compose ps
```

Services will automatically restart if they become unhealthy.

## Volumes

- `postgres_data`: Persistent PostgreSQL data
- `redis_data`: Redis cache data
- `memo_data`: Generated memos storage

## Troubleshooting

### Common Issues

1. **Services failing to start**: Check if required ports are available
2. **Database connection errors**: Ensure PostgreSQL is healthy before dependent services
3. **API key errors**: Verify all required environment variables are set
4. **Memory issues**: Increase Docker memory allocation for AI services

### Logs
```bash
# View all logs
docker-compose logs

# View specific service logs
docker-compose logs lbo-api

# Follow logs in real-time
docker-compose logs -f
```

## Architecture

The platform follows a microservices architecture with:
- Service isolation via Docker containers
- Health checks for reliability
- Automatic restart policies
- Shared network for service communication
- Persistent volumes for data storage

## Security Notes

- Database passwords are configured in docker-compose.yml
- API keys are managed via environment variables
- Services communicate over an internal Docker network
- Only necessary ports are exposed to the host