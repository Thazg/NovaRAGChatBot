from rag.cache import SimpleCache


def test_cache_evicts_least_recently_used_entry() -> None:
    cache = SimpleCache(max_entries=2)
    cache.set("first", 1)
    cache.set("second", 2)
    assert cache.get("first") == 1

    cache.set("third", 3)

    assert cache.get("first") == 1
    assert cache.get("second") is None
    assert cache.get("third") == 3


def test_cache_clear_removes_all_entries() -> None:
    cache = SimpleCache()
    cache.set("key", "value")

    cache.clear()

    assert cache.get("key") is None
