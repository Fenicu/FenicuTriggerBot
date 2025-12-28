.PHONY lint:
lint:
	echo "Running ruff..."
	uvx ruff check --config pyproject.toml --diff ./app

.PHONY format:
format:
	echo "Running ruff check with --fix..."
	uvx ruff check --config pyproject.toml --fix --unsafe-fixes ./app

.PHONY outdated:
outdated:
	uv tree --outdated --universal

.PHONY sync:
sync:
	uv sync --frozen

.PHONY pupgrade:
pupgrade:
	uv lock --upgrade

.PHONY upgrade:
upgrade:
	uv sync --upgrade
