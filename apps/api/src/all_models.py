"""Import every model module so the SQLAlchemy registry is complete.

The FastAPI app pulls models in through its routers, but standalone entry
points (the ARQ worker, scripts, alembic) don't — a missing import there
surfaces as 'could not find table X' when a ForeignKey resolves lazily.
Import this module from any non-FastAPI entry point.
"""

import src.domains.chat.models
import src.domains.documents.models
import src.domains.llm_settings.models
import src.domains.tenants.models
import src.domains.usage.models  # noqa: F401
