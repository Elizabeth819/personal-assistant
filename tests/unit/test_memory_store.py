from pa.memory.store import MemoryRecord, MemoryStore


def test_add_and_search() -> None:
    store = MemoryStore()
    store.add(MemoryRecord(id="1", text="buy coffee at Luckin"))
    store.add(MemoryRecord(id="2", text="call mom"))

    hits = store.search("coffee")
    assert len(hits) == 1
    assert hits[0].id == "1"


def test_search_limit() -> None:
    store = MemoryStore()
    for i in range(5):
        store.add(MemoryRecord(id=str(i), text="note"))
    assert len(store.search("note", limit=3)) == 3
