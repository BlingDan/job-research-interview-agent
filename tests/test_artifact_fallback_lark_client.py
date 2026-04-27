from pathlib import Path

from app.integrations.artifact_fallback_lark_client import ArtifactFallbackLarkClient
from app.integrations.fake_lark_client import FakeLarkClient


def test_artifact_fallback_client_continues_when_primary_doc_fails(tmp_path):
    class FailingPrimary(FakeLarkClient):
        def create_doc(self, task_id: str, title: str, content: str, task_dir: Path):
            raise RuntimeError("permission denied")

    client = ArtifactFallbackLarkClient(
        primary=FailingPrimary(base_url="https://real.local"),
        fallback=FakeLarkClient(base_url="https://fake.local"),
    )

    artifact = client.create_doc("task-1", "方案", "# 方案", Path(tmp_path))

    assert artifact.status == "fake"
    assert artifact.url == "https://fake.local/doc/task-1"
    assert "permission denied" in artifact.summary
