.PHONY: up migrate run build-images cleanup makemigrations shell check migrations-check test validate nginx-test nginx-start nginx-reload nginx-stop nginx-logs test-terminal test-actions test-docker test-dashboards

up:
	docker compose up -d

migrate:
	python manage.py migrate

run:
	python manage.py runserver

build-images:
	python manage.py build_task_images

cleanup:
	python manage.py cleanup_task_containers

makemigrations:
	python manage.py makemigrations

shell:
	python manage.py shell

check:
	python manage.py check

migrations-check:
	python manage.py makemigrations --check --dry-run

test:
	python manage.py test sandbox

test-terminal:
	python manage.py test sandbox.tests.test_terminal_auth sandbox.tests.test_terminal_gateway

test-actions:
	python manage.py test sandbox.tests.test_task_actions sandbox.tests.test_rerun_attempt

test-docker:
	python manage.py test sandbox.tests.test_docker_service sandbox.tests.test_management_commands

test-dashboards:
	python manage.py test sandbox.tests.test_trainee_dashboard sandbox.tests.test_mentor_dashboard

validate: check migrations-check test

nginx-test:
	nginx -p "$(PWD)" -c "$(PWD)/deploy/nginx/ticket-sandbox-local.conf" -t

nginx-start:
	mkdir -p logs
	nginx -p "$(PWD)" -c "$(PWD)/deploy/nginx/ticket-sandbox-local.conf"

nginx-reload:
	nginx -p "$(PWD)" -c "$(PWD)/deploy/nginx/ticket-sandbox-local.conf" -s reload

nginx-stop:
	nginx -p "$(PWD)" -c "$(PWD)/deploy/nginx/ticket-sandbox-local.conf" -s stop

nginx-logs:
	tail -f logs/nginx-error.log logs/nginx-access.log