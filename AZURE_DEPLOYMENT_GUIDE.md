# Azure Container Deployment Guide (Once everything's up and running...)

## Prerequisites

### Azure CLI Setup
```bash
# Install Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Login to Azure
az login

# Set subscription
az account set --subscription "your-subscription-id"
```

### Local Development Setup
```bash
# Copy environment file
cp .env.example .env

# Edit .env with your API keys
nano .env

# Build and run locally
docker-compose up --build
```

## Azure Resource Setup

### 1. Create Resource Group
```bash
az group create \
  --name lbo-microservices-rg \
  --location eastus
```

### 2. Create Container Registry
```bash
az acr create \
  --resource-group lbo-microservices-rg \
  --name lbomicroservicesacr \
  --sku Basic \
  --admin-enabled true
```

### 3. Create PostgreSQL Database
```bash
az postgres flexible-server create \
  --resource-group lbo-microservices-rg \
  --name lbo-postgres-server \
  --location eastus \
  --admin-user postgres \
  --admin-password "Admin0rbE" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --compute-generation 11 \
  --storage-size 32 \
  --version 15
```

### 4. Create Redis Cache
```bash
az redis create \
  --resource-group lbo-microservices-rg \
  --name lbo-redis-cache \
  --location eastus \
  --sku Basic \
  --vm-size c0
```

### 5. Configure Database Firewall
```bash
# Allow Azure services
az postgres flexible-server firewall-rule create \
  --resource-group lbo-microservices-rg \
  --server-name lbo-postgres-server \
  --rule-name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0

# Allow your IP (optional, for debugging)
az postgres flexible-server firewall-rule create \
  --resource-group lbo-microservices-rg \
  --server-name lbo-postgres-server \
  --rule-name AllowMyIP \
  --start-ip-address $(curl -s ifconfig.me) \
  --end-ip-address $(curl -s ifconfig.me)
```

## Container Deployment

### 1. Build and Push Container
```bash
# Get ACR login server
ACR_LOGIN_SERVER=$(az acr show \
  --name lbomicroservicesacr \
  --resource-group lbo-microservices-rg \
  --query loginServer \
  --output tsv)

# Login to ACR
az acr login --name lbomicroservicesacr

# Build and tag image
docker build -t $ACR_LOGIN_SERVER/lbo-api:latest .

# Push to ACR
docker push $ACR_LOGIN_SERVER/lbo-api:latest
```

### 2. Deploy Container Instance
```bash
# Get database connection string
DB_HOST=$(az postgres flexible-server show \
  --resource-group lbo-microservices-rg \
  --name lbo-postgres-server \
  --query fullyQualifiedDomainName \
  --output tsv)

# Get Redis connection string
REDIS_HOST=$(az redis show \
  --resource-group lbo-microservices-rg \
  --name lbo-redis-cache \
  --query hostName \
  --output tsv)

REDIS_KEY=$(az redis list-keys \
  --resource-group lbo-microservices-rg \
  --name lbo-redis-cache \
  --query primaryKey \
  --output tsv)

# Deploy container
az container create \
  --resource-group lbo-microservices-rg \
  --name lbo-api-container \
  --image $ACR_LOGIN_SERVER/lbo-api:latest \
  --cpu 1 \
  --memory 2 \
  --ports 8000 \
  --dns-name-label lbo-api-unique-name \
  --environment-variables \
    DB_HOST=$DB_HOST \
    DB_PORT=5432 \
    DB_USER=postgres \
    DB_PASSWORD=Admin0rbE \
    DB_NAME=finmetrics \
    REDIS_URL=redis://:$REDIS_KEY@$REDIS_HOST:6380 \
    FMP_API_KEY=$FMP_API_KEY \
    OPENAI_API_KEY=$OPENAI_API_KEY \
  --registry-login-server $ACR_LOGIN_SERVER \
  --registry-username lbomicroservicesacr \
  --registry-password $(az acr credential show \
    --name lbomicroservicesacr \
    --query passwords[0].value \
    --output tsv)
```

## Database Initialization

### 1. Install Database Schema
```bash
# Connect to the database and run models.py to create tables
# This can be done from a temporary container or your local machine

# Get database connection details
DB_HOST=$(az postgres flexible-server show \
  --resource-group lbo-microservices-rg \
  --name lbo-postgres-server \
  --query fullyQualifiedDomainName \
  --output tsv)

# Run initialization (from your local machine with psql installed)
PGPASSWORD=Admin0rbE psql -h $DB_HOST -U postgres -d finmetrics -c "\l"

# Or use a temporary container to run the schema creation
docker run --rm -it \
  -e DB_HOST=$DB_HOST \
  -e DB_PORT=5432 \
  -e DB_USER=postgres \
  -e DB_PASSWORD=Admin0rbE \
  -e DB_NAME=finmetrics \
  $ACR_LOGIN_SERVER/lbo-api:latest \
  python -c "
import asyncio
from models import create_tables

async def init_db():
    await create_tables()
    print('Database initialized successfully')

asyncio.run(init_db())
"
```

## Monitoring and Logging

### 1. View Container Logs
```bash
az container logs \
  --resource-group lbo-microservices-rg \
  --name lbo-api-container
```

### 2. Check Container Status
```bash
az container show \
  --resource-group lbo-microservices-rg \
  --name lbo-api-container \
  --query instanceView.state
```

### 3. Get Container IP and URL
```bash
# Get public IP
az container show \
  --resource-group lbo-microservices-rg \
  --name lbo-api-container \
  --query ipAddress.ip \
  --output tsv

# Get FQDN
az container show \
  --resource-group lbo-microservices-rg \
  --name lbo-api-container \
  --query ipAddress.fqdn \
  --output tsv
```

## Testing the Deployment

### 1. Health Check
```bash
# Get the container URL
CONTAINER_URL=$(az container show \
  --resource-group lbo-microservices-rg \
  --name lbo-api-container \
  --query ipAddress.fqdn \
  --output tsv)

# Test health endpoint
curl http://$CONTAINER_URL:8000/health
```

### 2. API Test
```bash
# Test root endpoint
curl http://$CONTAINER_URL:8000/

# Test LBO analysis (example)
curl -X POST http://$CONTAINER_URL:8000/api/v1/lbo/AAPL \
  -H "Content-Type: application/json"
```

## CI/CD with GitHub Actions

### 1. Create GitHub Secrets
Add these secrets to your GitHub repository:
- `AZURE_CREDENTIALS`: Service principal credentials
- `ACR_LOGIN_SERVER`: Container registry login server
- `ACR_USERNAME`: Container registry username
- `ACR_PASSWORD`: Container registry password
- `FMP_API_KEY`: Financial Modeling Prep API key
- `OPENAI_API_KEY`: OpenAI API key

### 2. GitHub Actions Workflow
Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Azure Container Instances

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Login to Azure
      uses: azure/login@v1
      with:
        creds: ${{ secrets.AZURE_CREDENTIALS }}
    
    - name: Build and push Docker image
      run: |
        docker build -t ${{ secrets.ACR_LOGIN_SERVER }}/lbo-api:${{ github.sha }} .
        docker login ${{ secrets.ACR_LOGIN_SERVER }} -u ${{ secrets.ACR_USERNAME }} -p ${{ secrets.ACR_PASSWORD }}
        docker push ${{ secrets.ACR_LOGIN_SERVER }}/lbo-api:${{ github.sha }}
    
    - name: Deploy to Azure Container Instances
      run: |
        az container create \
          --resource-group lbo-microservices-rg \
          --name lbo-api-container \
          --image ${{ secrets.ACR_LOGIN_SERVER }}/lbo-api:${{ github.sha }} \
          --cpu 1 \
          --memory 2 \
          --ports 8000 \
          --dns-name-label lbo-api-unique-name \
          --environment-variables \
            DB_HOST=$DB_HOST \
            DB_PORT=5432 \
            DB_USER=postgres \
            DB_PASSWORD=Admin0rbE \
            DB_NAME=finmetrics \
            REDIS_URL=$REDIS_URL \
            FMP_API_KEY=${{ secrets.FMP_API_KEY }} \
            OPENAI_API_KEY=${{ secrets.OPENAI_API_KEY }} \
          --registry-login-server ${{ secrets.ACR_LOGIN_SERVER }} \
          --registry-username ${{ secrets.ACR_USERNAME }} \
          --registry-password ${{ secrets.ACR_PASSWORD }}
```

## Cost Optimization

### 1. Container Instance Sizing
```bash
# Scale down for development
az container create \
  --cpu 0.5 \
  --memory 1

# Scale up for production
az container create \
  --cpu 2 \
  --memory 4
```

### 2. Auto-scaling (Container Apps Alternative)
For production workloads, consider Azure Container Apps for auto-scaling:

```bash
# Create Container Apps Environment
az containerapp env create \
  --name lbo-containerapp-env \
  --resource-group lbo-microservices-rg \
  --location eastus
```

## Troubleshooting

### Common Issues

1. **Container fails to start**: Check logs with `az container logs`
2. **Database connection fails**: Verify firewall rules and connection strings
3. **Redis connection fails**: Check Redis access keys and SSL settings
4. **API calls fail**: Verify environment variables and API keys

### Debug Commands
```bash
# Execute commands in running container
az container exec \
  --resource-group lbo-microservices-rg \
  --name lbo-api-container \
  --exec-command "/bin/bash"

# Restart container
az container restart \
  --resource-group lbo-microservices-rg \
  --name lbo-api-container
```

## Security Best Practices

1. **Use Azure Key Vault** for sensitive configuration
2. **Enable Azure Monitor** for logging and metrics
3. **Use managed identities** instead of service principal credentials
4. **Implement network security groups** for traffic filtering
5. **Regular security updates** for base images and dependencies

## Cleanup Resources

```bash
# Delete resource group (removes all resources)
az group delete \
  --name lbo-microservices-rg \
  --yes --no-wait
```
