.PHONY: help build up down restart logs shell db-shell redis-shell init-db import-sample test clean backup

# Default target
help:
	@echo "Caller-ID Rotation API - Available Commands:"
	@echo ""
	@echo "  make build          - Build Docker images"
	@echo "  make up             - Start all services"
	@echo "  make down           - Stop all services"
	@echo "  make restart        - Restart all services"
	@echo "  make logs           - View logs (all services)"
	@echo "  make logs-api       - View API logs only"
	@echo "  make shell          - Open shell in API container"
	@echo "  make db-shell       - Open PostgreSQL shell"
	@echo "  make redis-shell    - Open Redis CLI"
	@echo "  make init-db        - Initialize database tables"
	@echo "  make init-db-sample - Initialize database with sample data"
	@echo "  make import-sample  - Generate and import sample caller-IDs"
	@echo "  make test           - Run tests"
	@echo "  make health         - Check API health"
	@echo "  make stats          - Get API statistics"
	@echo "  make backup         - Backup database and Redis"
	@echo "  make clean          - Remove all containers and volumes"
	@echo ""

# Build Docker images
build:
	docker-compose build

# Start all services
up:
	docker-compose up -d
	@echo "Services started. Check status with 'make logs'"

# Stop all services
down:
	docker-compose down

# Restart all services
restart:
	docker-compose restart

# View logs
logs:
	docker-compose logs -f

# View API logs only
logs-api:
	docker logs -f callerid_api

# Open shell in API container
shell:
	docker exec -it callerid_api /bin/bash

# Open PostgreSQL shell
db-shell:
	docker exec -it callerid_postgres psql -U callerid_user -d callerid_db

# Open Redis CLI
redis-shell:
	docker exec -it callerid_redis redis-cli

# Initialize database
init-db:
	docker exec -it callerid_api python3 scripts/init_db.py

# Initialize database with sample data
init-db-sample:
	docker exec -it callerid_api python3 scripts/init_db.py --sample-data

# Generate and import sample caller-IDs
import-sample:
	@echo "Generating 1000 sample caller-IDs..."
	docker exec -it callerid_api python3 scripts/bulk_import.py \
		--generate-sample /app/data/sample_1000.csv \
		--sample-count 1000
	@echo "Importing to database..."
	docker exec -it callerid_api python3 scripts/bulk_import.py \
		--csv /app/data/sample_1000.csv \
		--method db
	@echo "Done!"

# Run tests (if implemented)
test:
	@echo "Running tests..."
	docker exec -it callerid_api pytest tests/ -v

# Check API health
health:
	@curl -s http://127.0.0.1:8000/health | python3 -m json.tool

# Get API statistics (requires ADMIN_TOKEN env var)
stats:
	@if [ -z "$(ADMIN_TOKEN)" ]; then \
		echo "Error: ADMIN_TOKEN not set"; \
		echo "Usage: ADMIN_TOKEN=your_token make stats"; \
		exit 1; \
	fi
	@curl -s http://127.0.0.1:8000/api/stats \
		-H "Authorization: Bearer $(ADMIN_TOKEN)" | python3 -m json.tool

# Backup database and Redis
backup:
	@mkdir -p backups
	@echo "Backing up PostgreSQL..."
	@docker exec callerid_postgres pg_dump -U callerid_user callerid_db > \
		backups/callerid_db_$$(date +%Y%m%d_%H%M%S).sql
	@echo "Backing up Redis..."
	@docker exec callerid_redis redis-cli SAVE
	@docker cp callerid_redis:/data/dump.rdb \
		backups/redis_$$(date +%Y%m%d_%H%M%S).rdb
	@echo "Backup complete! Files saved in backups/"

# Clean up everything (WARNING: Destroys all data!)
clean:
	@echo "WARNING: This will remove all containers and volumes!"
	@read -p "Are you sure? [y/N] " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		docker-compose down -v; \
		echo "Cleaned up!"; \
	else \
		echo "Cancelled."; \
	fi

# Show container status
status:
	docker-compose ps

# Show container resource usage
stats-docker:
	docker stats --no-stream

# View recent API requests
recent-logs:
	docker exec -it callerid_postgres psql -U callerid_user -d callerid_db \
		-c "SELECT timestamp, endpoint, agent, campaign, caller_id_allocated, response_time_ms, status_code FROM api_logs ORDER BY timestamp DESC LIMIT 20;"

# Count caller-IDs
count-cids:
	docker exec -it callerid_postgres psql -U callerid_user -d callerid_db \
		-c "SELECT COUNT(*) as total, SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active FROM caller_ids;"

# Show active reservations
active-reservations:
	docker exec -it callerid_redis redis-cli KEYS "reservation:*" | wc -l
