.PHONY: help dev test prod build clean logs health

# Default target
help:
	@echo "Available targets:"
	@echo "  dev     - Start development environment"
	@echo "  test    - Run tests"
	@echo "  prod    - Start production environment"
	@echo "  build   - Build all Docker images"
	@echo "  clean   - Clean up containers and images"
	@echo "  logs    - Show logs for all services"
	@echo "  health  - Check health of all services"
	@echo "  stop    - Stop all services"

dev:
	@echo "Starting development environment..."
	@if [ ! -f .env ]; then echo "Creating .env from .env.example"; cp .env.example .env; fi
	docker-compose up -d
	@echo "Development environment started!"
	@echo "Services available at:"
	@echo "  - LBO API: http://localhost:8000"
	@echo "  - Text Extraction: http://localhost:8061"
	@echo "  - Analysis: http://localhost:8001"
	@echo "  - Unified API: http://localhost:8080"
	@echo "  - Chatbot: http://localhost:8090"

test:
	@echo "Running tests..."
	docker-compose up -d postgres redis
	@echo "Waiting for services to be ready..."
	sleep 30
	docker-compose exec postgres pg_isready -U postgres
	docker-compose exec redis redis-cli ping
	@echo "Basic connectivity tests passed!"

prod:
	@echo "Starting production environment..."
	@if [ ! -f .env ]; then echo "ERROR: .env file required for production"; exit 1; fi
	docker-compose -f docker-compose.yml up -d
	@echo "Production environment started!"

build:
	@echo "Building all Docker images..."
	docker-compose build
	@echo "All images built successfully!"

clean:
	@echo "Cleaning up containers and images..."
	docker-compose down -v
	docker system prune -f
	@echo "Cleanup completed!"

logs:
	@echo "Showing logs for all services..."
	docker-compose logs -f

health:
	@echo "Checking health of all services..."
	docker-compose ps
	@echo "\nTesting service endpoints..."
	@curl -f http://localhost:8000/health || echo "LBO API not responding"
	@curl -f http://localhost:8061/health || echo "Text Extraction not responding"
	@curl -f http://localhost:8001/health || echo "Analysis not responding"
	@curl -f http://localhost:8080/health || echo "Unified API not responding"
	@curl -f http://localhost:8090/health || echo "Chatbot not responding"

stop:
	@echo "Stopping all services..."
	docker-compose down
	@echo "All services stopped!"

# Quick smoke test
smoke:
	@echo "Running 30-second smoke test..."
	@make dev
	@sleep 30
	@make health
	@echo "\nSmoke test completed! ✓"