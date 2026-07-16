import json
import threading
from pathlib import Path

from pipeline import checkpoints as C
from pipeline.atomic_write import atomic_write_json, atomic_write_text


def test_atomic_write_and_read(tmp_path: Path):
    C.write_state(tmp_path, {"last_step": 1, "stages": {}})
    assert C.read_state(tmp_path)["last_step"] == 1


def test_mark_substep_done_is_atomic(tmp_path: Path):
    C.write_state(tmp_path, {"last_step": 0})
    C.mark_substep_done(tmp_path, "s1", "draft", last_step=3)
    s = C.read_state(tmp_path)
    # substep flag and last_step advance together (single atomic write)
    assert s["stages"]["s1"]["substeps"]["draft"] == "done"
    assert s["last_step"] == 3


def test_auto_repair_from_backup(tmp_path: Path):
    C.write_state(tmp_path, {"last_step": 5})
    C.write_state(tmp_path, {"last_step": 6})  # creates a backup of step 5
    (tmp_path / "state.json").write_text("{ broken json", encoding="utf-8")
    recovered = C.read_state(tmp_path)  # falls back to a valid backup
    assert recovered.get("last_step") in (5, 6)


def test_concurrent_patches_do_not_corrupt(tmp_path: Path):
    C.write_state(tmp_path, {"counters": {}})

    def worker(i: int):
        C.write_state_patch(tmp_path, {f"counters.k{i}": i}, backup=False)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = C.read_state(tmp_path)
    # valid JSON and every writer's key survived (fcntl-serialized RMW)
    assert len(final["counters"]) == 20
    assert final["counters"]["k7"] == 7


def test_atomic_write_json_text(tmp_path: Path):
    p = tmp_path / "x.json"
    atomic_write_json(p, {"a": 1})
    assert json.loads(p.read_text())["a"] == 1
    t = tmp_path / "x.txt"
    atomic_write_text(t, "hello")
    assert t.read_text() == "hello"
