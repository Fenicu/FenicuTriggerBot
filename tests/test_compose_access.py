from pathlib import Path

import yaml


def test_compose_database_is_loopback_and_workers_wait_for_broker():
    services = yaml.safe_load(Path("compose.yml").read_text())["services"]
    assert services["postgres"]["ports"] == ["127.0.0.1:${POSTGRES_PUB_PORT:-5432}:5432"]
    for service in ("bot", "ai_worker"):
        assert services[service]["depends_on"]["rabbitmq"]["condition"] == "service_healthy"
