import type { ArtifactPreview, TaskArtifact } from "../types";

interface ArtifactPreviewPanelProps {
  artifacts: TaskArtifact[];
  selectedKind: string | null;
  onSelectKind: (kind: "doc" | "slides" | "canvas") => void;
  preview: ArtifactPreview | null;
}

export function ArtifactPreviewPanel({
  artifacts,
  selectedKind,
  onSelectKind,
  preview,
}: ArtifactPreviewPanelProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Artifacts</p>
          <h3>Preview</h3>
        </div>
      </div>
      <div className="artifact-tabs">
        {artifacts.map((artifact) => (
          <button
            key={artifact.artifact_id}
            className={`artifact-tab ${selectedKind === artifact.kind ? "selected" : ""}`}
            onClick={() => onSelectKind(artifact.kind)}
            type="button"
          >
            {artifact.kind}
          </button>
        ))}
      </div>
      {preview ? (
        <div className="artifact-preview">
          <div className="artifact-meta">
            <strong>{preview.title}</strong>
            <span>{preview.status}</span>
          </div>
          {preview.url ? (
            <a href={preview.url} target="_blank" rel="noreferrer">
              Open artifact
            </a>
          ) : null}
          <pre>{preview.content || preview.summary || "No preview content available."}</pre>
        </div>
      ) : (
        <p className="empty-copy">Select an artifact to preview its content.</p>
      )}
    </section>
  );
}
