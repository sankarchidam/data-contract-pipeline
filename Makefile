.PHONY: up down logs ps test demo-compatible demo-breaking clean

up:
	docker compose up --build -d
	@echo ""
	@echo "Kafka:            localhost:9092"
	@echo "Apicurio Registry: http://localhost:8080"
	@echo "Tail logs with:    make logs"

down:
	docker compose down

logs:
	docker compose logs -f producer consumer

ps:
	docker compose ps

# Local, fast-feedback data-contract check (same script CI runs).
test:
	pip install -q -r scripts/requirements.txt
	docker compose up -d schema-registry
	python scripts/register_schema.py orders.order-created-value \
		schemas/order-created/schema.avsc \
		--registry-url http://localhost:8080/apis/ccompat/v7 \
		--set-compatibility BACKWARD --wait
	pytest tests/ -v

# Demo: a change that adds an optional field with a default -> passes.
demo-compatible:
	python scripts/check_compatibility.py orders.order-created-value \
		demo/schema-compatible-v2.avsc \
		--registry-url http://localhost:8080/apis/ccompat/v7

# Demo: a change that adds a required field with no default -> blocked.
demo-breaking:
	python scripts/check_compatibility.py orders.order-created-value \
		demo/schema-breaking-v2.avsc \
		--registry-url http://localhost:8080/apis/ccompat/v7

clean:
	docker compose down -v --remove-orphans
