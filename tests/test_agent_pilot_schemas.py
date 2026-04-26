from app.schemas.agent_pilot import AgentPilotTask, ArtifactRef


def test_task_defaults_start_created():
    task = AgentPilotTask(task_id="task-1", input_text="生成参赛方案")

    assert task.status == "CREATED"
    assert task.artifacts == []
    assert task.revisions == []


def test_artifact_ref_supports_fake_doc():
    artifact = ArtifactRef(
        artifact_id="artifact-1",
        kind="doc",
        title="Agent-Pilot 参赛方案",
        status="fake",
        url="https://fake.feishu.local/doc/task-1",
    )

    assert artifact.kind == "doc"
    assert artifact.status == "fake"

