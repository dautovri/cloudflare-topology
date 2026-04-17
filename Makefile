.PHONY: build run stop clean dev test lint

# Docker image name
IMAGE_NAME := cloudflare-topology
CONTAINER_NAME := cloudflare-topology

# Default port
PORT ?= 8080

# Build the Docker image
build:
	docker build -t $(IMAGE_NAME) .

# Run the container
run:
	@if [ -z "$$CLOUDFLARE_API_TOKEN" ]; then \
		echo "Error: CLOUDFLARE_API_TOKEN is not set"; \
		exit 1; \
	fi
	@if [ -z "$$CLOUDFLARE_ACCOUNT_ID" ]; then \
		echo "Error: CLOUDFLARE_ACCOUNT_ID is not set"; \
		exit 1; \
	fi
	docker run -d \
		--name $(CONTAINER_NAME) \
		-p $(PORT):8080 \
		-e CLOUDFLARE_API_TOKEN="$$CLOUDFLARE_API_TOKEN" \
		-e CLOUDFLARE_ACCOUNT_ID="$$CLOUDFLARE_ACCOUNT_ID" \
		$(IMAGE_NAME)
	@echo "Container started. Access at http://localhost:$(PORT)"

# Run interactively (for debugging)
run-it:
	@if [ -z "$$CLOUDFLARE_API_TOKEN" ]; then \
		echo "Error: CLOUDFLARE_API_TOKEN is not set"; \
		exit 1; \
	fi
	@if [ -z "$$CLOUDFLARE_ACCOUNT_ID" ]; then \
		echo "Error: CLOUDFLARE_ACCOUNT_ID is not set"; \
		exit 1; \
	fi
	docker run -it --rm \
		--name $(CONTAINER_NAME) \
		-p $(PORT):8080 \
		-e CLOUDFLARE_API_TOKEN="$$CLOUDFLARE_API_TOKEN" \
		-e CLOUDFLARE_ACCOUNT_ID="$$CLOUDFLARE_ACCOUNT_ID" \
		$(IMAGE_NAME)

# Stop the container
stop:
	docker stop $(CONTAINER_NAME) || true
	docker rm $(CONTAINER_NAME) || true

# Clean up Docker resources
clean: stop
	docker rmi $(IMAGE_NAME) || true

# Local development - install dependencies
dev-setup:
	python -m pip install -r requirements.txt

# Local development - run the mapper
dev:
	python main.py --debug

# Run tests
test:
	python -m pytest tests/ -v

# Run linting
lint:
	python -m flake8 . --max-line-length=120 --exclude=venv,__pycache__
	python -m mypy . --ignore-missing-imports

# View logs
logs:
	docker logs -f $(CONTAINER_NAME)

# Regenerate topology in running container (requires REGEN_AUTH_TOKEN env var)
regenerate:
	@if [ -z "$$REGEN_AUTH_TOKEN" ]; then \
		echo "Error: set REGEN_AUTH_TOKEN to the same value used when starting the container"; \
		exit 1; \
	fi
	curl -X POST -H "Authorization: Bearer $$REGEN_AUTH_TOKEN" http://localhost:$(PORT)/regenerate

# Help
help:
	@echo "Cloudflare Network Topology Mapper"
	@echo ""
	@echo "Usage:"
	@echo "  make build        Build Docker image"
	@echo "  make run          Run container (requires CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID)"
	@echo "  make run-it       Run container interactively"
	@echo "  make stop         Stop and remove container"
	@echo "  make clean        Remove container and image"
	@echo "  make dev-setup    Install dependencies for local development"
	@echo "  make dev          Run locally in debug mode"
	@echo "  make test         Run tests"
	@echo "  make lint         Run linting"
	@echo "  make logs         View container logs"
	@echo "  make regenerate   Trigger topology regeneration"
	@echo ""
	@echo "Environment Variables:"
	@echo "  CLOUDFLARE_API_TOKEN   - Cloudflare API token (required)"
	@echo "  CLOUDFLARE_ACCOUNT_ID  - Cloudflare account ID (required)"
	@echo "  PORT                   - Port to expose (default: 8080)"

.PHONY: deploy-demo
deploy-demo:
	python main.py --demo --no-browser --output _deploy/index.html
	cp -R lib _deploy/ 2>/dev/null || true
	npx wrangler pages deploy _deploy --project-name=cloudflare-topology --branch=main --commit-dirty=true
