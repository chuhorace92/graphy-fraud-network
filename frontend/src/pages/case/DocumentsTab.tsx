import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { api } from "../../api/client";
import { formatDate } from "../../lib/friendly";
import { Icon } from "../../ui/Icon";
import { Chip, EmptyState, ErrorNote } from "../../ui/kit";
import { bytes, type TabProps } from "./shared";

const MAX_BYTES = 10 * 1024 * 1024;

/** Files kept with the case: bank statements, correspondence, screenshots. Up to 10 MB each, and
 *  each can be tagged to the task it answers. */
export function DocumentsTab({ caseKey, detail, canAct, saved }: TabProps) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [task, setTask] = useState("");
  const tooBig = !!file && file.size > MAX_BYTES;
  const upload = useMutation({
    mutationFn: () => api.uploadCaseDocument(caseKey, file!, note.trim(), task || null),
    onSuccess: (d) => {
      setFile(null);
      setNote("");
      if (input.current) input.current.value = "";
      saved(d);
    },
  });
  const remove = useMutation({ mutationFn: (id: string) => api.deleteCaseDocument(caseKey, id), onSuccess: saved });
  const retag = useMutation({
    mutationFn: (v: { id: string; task: string }) => api.tagCaseDocument(caseKey, v.id, v.task || null),
    onSuccess: saved,
  });
  const taskOptions = (
    <>
      <option value="">No task</option>
      {detail.tasks.map((t) => (
        <option key={t.id} value={t.id}>
          {t.title}
        </option>
      ))}
    </>
  );
  return (
    <div className="documents">
      {canAct && (
        <form
          className="task-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (file && !tooBig) upload.mutate();
          }}
        >
          <input
            ref={input}
            type="file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            aria-label="File to attach"
          />
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="What is this? (optional)"
            maxLength={500}
            aria-label="Note about the file"
          />
          <select value={task} onChange={(e) => setTask(e.target.value)} aria-label="Tag to a task">
            {taskOptions}
          </select>
          <button type="submit" className="btn primary" disabled={!file || tooBig || upload.isPending}>
            <Icon name="upload" size={16} /> Upload
          </button>
        </form>
      )}
      {tooBig && <p className="field-error">That file is {bytes(file!.size)}; the limit is 10 MB.</p>}
      {(upload.isError || remove.isError || retag.isError) && (
        <ErrorNote error={upload.error ?? remove.error ?? retag.error} />
      )}
      {detail.documents.length === 0 ? (
        <EmptyState icon="file" title="No documents yet">
          Attach the records the case relies on, such as statements, emails and screenshots.
        </EmptyState>
      ) : (
        <ul className="item-list">
          {detail.documents.map((d) => (
            <li key={d.id} className="item">
              <span className="item-icon">
                <Icon name="file" size={16} />
              </span>
              <div className="item-main">
                <a className="strong" href={api.caseDocumentUrl(caseKey, d.id)} download={d.filename}>
                  {d.filename}
                </a>
                {d.note && <p>{d.note}</p>}
                <span className="muted small">
                  {bytes(d.size)} · {d.uploaded_by} · {formatDate(d.created_at)}
                </span>
              </div>
              {canAct ? (
                <select
                  className="tag-select"
                  value={d.task_id ?? ""}
                  disabled={retag.isPending}
                  onChange={(e) => retag.mutate({ id: d.id, task: e.target.value })}
                  aria-label={`Task for ${d.filename}`}
                  title="Tag to a task"
                >
                  {taskOptions}
                </select>
              ) : (
                d.task_id && <Chip tone="accent">Task</Chip>
              )}
              <a
                className="icon-btn"
                href={api.caseDocumentUrl(caseKey, d.id)}
                download={d.filename}
                title="Download"
                aria-label={`Download ${d.filename}`}
              >
                <Icon name="download" size={16} />
              </a>
              {canAct && (
                <button
                  type="button"
                  className="icon-btn"
                  title="Delete document"
                  aria-label={`Delete ${d.filename}`}
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(d.id)}
                >
                  <Icon name="trash" size={16} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
