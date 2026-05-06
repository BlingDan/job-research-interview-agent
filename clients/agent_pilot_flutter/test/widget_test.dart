import "package:agent_pilot_flutter/core/models.dart";
import "package:agent_pilot_flutter/shared/screens/task_detail_screen.dart";
import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";


void main() {
  testWidgets("task detail screen shows shared task data and allowed actions", (
    WidgetTester tester,
  ) async {
    const snapshot = SurfaceTaskSnapshot(
      surface: "windows",
      taskId: "task-123",
      status: "waiting_user",
      inputText: "Create an office collaboration package",
      summary: "Shared state waiting for confirmation.",
      updatedAt: "2026-05-06T16:00:00Z",
      actions: [
        TaskAction(
          type: "confirm",
          label: "Confirm task",
          taskId: "task-123",
          description: "Continue the current plan.",
          endpoint: "/api/assistant/tasks/task-123/actions/confirm",
        ),
        TaskAction(
          type: "reset",
          label: "Reset binding",
          taskId: "task-123",
          description: "Clear the current IM binding.",
          endpoint: "/api/assistant/tasks/task-123/actions/reset",
        ),
      ],
      artifacts: [
        TaskArtifact(
          artifactId: "artifact-doc",
          kind: "doc",
          title: "Proposal",
          status: "created",
          summary: "Initial proposal ready.",
          url: null,
        ),
      ],
      steps: [
        TaskStep(
          id: "step-1",
          title: "Plan the task",
          goal: "Create the shared execution plan.",
          agent: "PlannerAgent",
          tool: "plan_task",
          status: "waiting_input",
          expectedArtifact: "doc",
        ),
      ],
    );

    await tester.pumpWidget(
      MaterialApp(
        home: TaskDetailScreen(
          snapshot: snapshot,
          onConfirm: () async {},
          onReset: () async {},
          onRevise: () async {},
        ),
      ),
    );

    expect(find.text("task-123"), findsOneWidget);
    expect(find.text("Create an office collaboration package"), findsOneWidget);
    expect(find.text("Confirm"), findsOneWidget);
    expect(find.text("Reset"), findsOneWidget);
    expect(find.text("Revise"), findsOneWidget);

    final confirmButton = tester.widget<FilledButton>(find.byType(FilledButton));
    expect(confirmButton.onPressed, isNotNull);

    final reviseButton = tester.widgetList<OutlinedButton>(find.byType(OutlinedButton)).first;
    expect(reviseButton.onPressed, isNull);
  });
}
