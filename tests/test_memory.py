from src.memory import MemoryStore


def test_memory_dedupes_events(tmp_path) -> None:
    store = MemoryStore(str(tmp_path / "state.json"))
    store.add_events([{"id": "evt_1"}, {"id": "evt_1"}])
    assert len(store.state["events"]) == 1


def test_memory_rejection_ttl(tmp_path) -> None:
    store = MemoryStore(str(tmp_path / "state.json"))
    store.increment_run_count()
    store.set_approval("evt_1", False)
    store.increment_run_count()
    assert "evt_1" in store.get_blocked_event_ids(ttl_runs=2)
