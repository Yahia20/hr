"""The SPA shell must revalidate so a deploy reaches users on their next load;
fingerprinted assets can be cached for good; API data must never be stored."""


def test_cache_policy_by_path(client):
    assert client.get("/api/auth/me").headers["cache-control"] == "no-store"
    assert client.get("/health").headers["cache-control"] == "no-cache"
    assert client.get("/assets/index-abc123.js").headers["cache-control"] == "public, max-age=31536000, immutable"
