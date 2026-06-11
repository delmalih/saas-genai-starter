"""Export the OpenAPI schema to stdout.

Used by `make generate-client` — run from apps/api with PYTHONPATH=. so `src` resolves.
"""

import json
import sys

from src.main import app

sys.stdout.write(json.dumps(app.openapi(), indent=2) + "\n")
