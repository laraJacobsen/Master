"""The frontend build fingerprint (backend/main.frontend_build): written into every served
page and reported by the status poll, so open tabs notice an `npm run build`."""

import re

from fastapi.testclient import TestClient

from backend import main


def test_pages_carry_the_build_and_status_reports_it(tmp_path, monkeypatch):
    (tmp_path / "student.html").write_text("<html><head><title>s</title></head><body></body></html>")
    (tmp_path / "setup.html").write_text("<html><head></head><body>setup</body></html>")
    monkeypatch.setattr(main, "_frontend_dir", str(tmp_path))
    monkeypatch.setattr(main, "_build_cache", {"key": None, "build": None})
    with TestClient(main.app) as client:
        page = client.get("/join")
        assert page.headers["cache-control"] == "no-cache"
        served = re.search(r'<meta name="app-build" content="(\w+)">', page.text).group(1)
        assert client.get("/api/lecture/status").json()["build"] == served
        assert client.get("/api/build").json() == {"build": served}  # the lecturer pages' check

        # A rebuild changes the pages (their asset names): a new build id.
        (tmp_path / "student.html").write_text("<html><head><title>s2</title></head><body></body></html>")
        import os
        os.utime(tmp_path / "student.html", (1, 1))  # a different mtime, however fast the test runs
        assert client.get("/api/lecture/status").json()["build"] not in (None, served)


def test_no_build_without_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "_frontend_dir", str(tmp_path / "missing"))
    monkeypatch.setattr(main, "_build_cache", {"key": None, "build": None})
    assert main.frontend_build() is None
