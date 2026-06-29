"""Self-check: TestClient smoke test for the GUI backend.

The one runnable check the pragmaticefficient rule leaves behind — fails fast if
routing/data wiring breaks. Run: `python -m pipeline_frontend_gui.selfcheck`
"""

from fastapi.testclient import TestClient

from pipeline_frontend_gui.app import app


def main() -> int:
    client = TestClient(app)
    checks = []
    for path in ["/api/health", "/api/status", "/api/results", "/api/config"]:
        r = client.get(path)
        checks.append((path, r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text))
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text}"

    # index + a static asset resolve
    assert client.get("/").status_code == 200, "index did not serve"
    assert client.get("/static/app.js").status_code == 200, "app.js did not serve"

    # invalid phase is rejected
    assert client.post("/api/run", json={"phase": "bogus"}).status_code == 400

    # config round-trip
    cfg = client.get("/api/config").json()
    assert client.post("/api/config", json=cfg).status_code == 200, "config save failed"

    for path, code, _ in checks:
        print(f"[OK] GET {path} -> {code}")
    print("[OK] GET / -> 200")
    print("[OK] GET /static/app.js -> 200")
    print("[OK] POST /api/run invalid phase -> 400")
    print("[OK] POST /api/config round-trip -> 200")
    print("\nAll GUI self-checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
