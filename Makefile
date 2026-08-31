.PHONY: up down logs

# Bring up the infrastructure services (Postgres for now; more added as
# the stack grows). Waits until each reports healthy.
up:
	docker compose up -d --wait

down:
	docker compose down

logs:
	docker compose logs -f
