include .env

# To initialize `.venv`: `python3 -m venv .venv`.

run-flask:
	.\.venv\Scripts\activate
	set FLASK_APP=.\app.py
	flask run --host=$(HOST) --port=$(PORT)

# Or, if that doesn't work: python app.py --host=0.0.0.0 --port=3123

# TODO: Doesn't work for some reason. Currently have to run each command manually.
run-flask-linux:
	. .venv/bin/activate
	export FLASK_APP=./app.py
	flask run --host=$(HOST) --port=$(PORT)



local-encryption-key:
	@echo "Generating encryption key..."
	@python3 -c "import secrets, string; print('ENCRYPTION_KEY=' + ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32)))"



mypy:
	mypy --explicit-package-bases lib settings.py


# Docker
auth:
	aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $(DOCKER_REGISTRY)

create-repos:
	aws ecr create-repository --repository-name $(FLASK_IMAGE) --region us-east-1 || true

docker-flask:
	docker build --build-arg PORT=$(FLASK_PORT) -t $(DOCKER_REGISTRY)/$(FLASK_IMAGE):$(FLASK_VERSION) -f Dockerfile.flask .
	docker push $(DOCKER_REGISTRY)/$(FLASK_IMAGE):$(FLASK_VERSION)
	kubectl rollout restart deployment $(FLASK_DEPLOYMENT) --namespace=$(NAMESPACE)



# Tests
test-crud:
	python test_api.py

test-schema:
	python test_schema.py

test-surrealdb:
	python test_db.py

test-create-and-retrieve:
	python test_create_and_retrieve.py



# Celery
CELERY_IMAGE=celery-worker
CELERY_VERSION=1.0.0


celery-docker:
	docker build -t $(CELERY_IMAGE):$(CELERY_VERSION) -f Dockerfile.celery .

celery-run:
	docker run -d --name celery-worker -e CELERY_BROKER_URL=redis://$(REDIS_HOST):$(REDIS_PORT)/1 -e SENTRY_DSN=$(SENTRY_DSN) -e CELERY_RESULT_BACKEND=redis://$(REDIS_HOST):$(REDIS_PORT)/1 $(CELERY_IMAGE):$(CELERY_VERSION)

