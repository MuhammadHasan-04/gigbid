"""Write the OpenAPI schema used to generate the TypeScript client (make api-client)."""
import json
import sys

from apps.api.main import app

json.dump(app.openapi(), open(sys.argv[1] if len(sys.argv) > 1 else "apps/web/openapi.json", "w"), indent=1)
