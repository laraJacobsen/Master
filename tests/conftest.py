"""Runs before any test module is imported: every test uses a throwaway database, never
backend/prototype.db (store.DB_PATH is read once, when backend.store is imported)."""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="lecture-tests-")
os.environ["PROTOTYPE_DB_PATH"] = os.path.join(_tmp, "test.db")
os.environ.pop("LECTURER_PASSWORD", None)

from backend import store  # noqa: E402

assert store.DB_PATH.startswith(_tmp), store.DB_PATH
store.init_db()
