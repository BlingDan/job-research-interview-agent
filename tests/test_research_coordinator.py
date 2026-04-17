import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.research_coordinator import ResearchCoordinator


def test_write_json_persists_serialized_utf8_content():
    with TemporaryDirectory() as temp_dir:
        coordinator = ResearchCoordinator.__new__(ResearchCoordinator)
        coordinator.task_dir = Path(temp_dir)

        payload = {"message": "你好", "count": 1}

        coordinator._write_json("state.json", payload)

        written = (coordinator.task_dir / "state.json").read_text(encoding="utf-8")

        assert json.loads(written) == payload
        assert '"message": "你好"' in written
