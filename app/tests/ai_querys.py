from ..modules.ai.services import list_providers, get_provider
from ..core.database import get_db

db = get_db()

print(list_providers(db))
print("#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=")
print(list_providers(db, {"is_active", True}))
print("#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=")
print(list_providers(db, {"is_active", False}))
print("#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=#=")
print(get_provider("Q222-58:944", db))
