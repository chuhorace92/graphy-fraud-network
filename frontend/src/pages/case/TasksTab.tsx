import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../../api/client";
import type { CaseDetail, CaseTask, TaskStatus } from "../../api/types";
import { formatDate, initials, plural } from "../../lib/friendly";
import { textToHtml } from "../../lib/notes";
import { useMe } from "../../lib/useMe";
import { Icon } from "../../ui/Icon";
import { Chip, EmptyState, ErrorNote } from "../../ui/kit";
import { bytes, isClosed, type TabProps } from "./shared";

const STATUS: { value: TaskStatus; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "received", label: "Received" },
  { value: "not_received", label: "Not received" },
];

const today = () => new Date().toISOString().slice(0, 10);

type Patch = Parameters<typeof api.updateCaseTask>[2];

/** Requests and checks to make on the case: who owns each, when it is due, whether it came back,
 *  and the documents and notes that belong to it. */
export function TasksTab({ caseKey, detail, canAct, saved }: TabProps) {
  const { me } = useMe();
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [mine, setMine] = useState(true);
  const [editing, setEditing] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [noteText, setNoteText] = useState("");
  const closedCase = isClosed(detail.summary.status);
  const add = useMutation({
    mutationFn: async () => {
      const before = new Set(detail.tasks.map((t) => t.id));
      let d = await api.addCaseTask(caseKey, {
        title: title.trim(), due_date: due || null, assignee: mine && me ? me.subject : null,
      });
      const made = d.tasks.find((t) => !before.has(t.id));
      if (made) {
        for (const f of files) d = await api.uploadCaseDocument(caseKey, f, "", made.id);
        if (noteText.trim()) d = await api.addCaseNote(caseKey, { title: "", body: textToHtml(noteText), task_id: made.id });
      }
      return d;
    },
    onSuccess: (d) => {
      setTitle("");
      setDue("");
      setFiles([]);
      setNoteText("");
      saved(d);
    },
  });
  const change = useMutation({
    mutationFn: (v: { id: string; patch: Patch }) => api.updateCaseTask(caseKey, v.id, v.patch),
    onSuccess: (d) => {
      setEditing(null);
      saved(d);
    },
  });
  const remove = useMutation({ mutationFn: (id: string) => api.deleteCaseTask(caseKey, id), onSuccess: saved });
  const busy = add.isPending || change.isPending || remove.isPending;

  const { tasks } = detail;
  const closed = tasks.filter((t) => t.done).length;
  return (
    <div className="tasks">
      {canAct && (
        <form
          className="task-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (title.trim()) add.mutate();
          }}
        >
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Add a request or task, e.g. “Request bank account ownership records”"
            maxLength={255}
            aria-label="Task"
          />
          <input type="date" value={due} onChange={(e) => setDue(e.target.value)} aria-label="Due date" />
          <label className="check">
            <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> Assign to me
          </label>
          <button type="submit" className="btn primary" disabled={!title.trim() || add.isPending}>
            Add task
          </button>
          <details className="task-attach">
            <summary>
              Attach files or a note{files.length || noteText.trim() ? ` (${files.length} files${noteText.trim() ? ", 1 note" : ""})` : ""}
            </summary>
            <div className="task-attach-body">
              <input
                type="file"
                multiple
                onChange={(e) => setFiles([...(e.target.files ?? [])])}
                aria-label="Files to attach to the task"
              />
              {!closedCase && (
                <textarea
                  value={noteText}
                  onChange={(e) => setNoteText(e.target.value)}
                  placeholder="A note about this task (it is added to the Notes tab, tagged to the task)"
                  rows={2}
                  maxLength={4000}
                  aria-label="Note about the task"
                />
              )}
              <span className="muted small">They are tagged to the task when it is created. Files up to 10 MB.</span>
            </div>
          </details>
        </form>
      )}
      {(add.isError || change.isError || remove.isError) && (
        <ErrorNote error={add.error ?? change.error ?? remove.error} />
      )}
      {tasks.length === 0 ? (
        <EmptyState icon="tasks" title="No tasks yet">
          Break the investigation into steps: who to call, what to request, what to check.
        </EmptyState>
      ) : (
        <>
          <div className="progress" aria-label={`${closed} of ${tasks.length} tasks closed`}>
            <span className="muted small">
              {closed} of {tasks.length} closed
            </span>
            <span className="share">
              <i style={{ width: `${(closed / tasks.length) * 100}%` }} />
            </span>
          </div>
          <table className="data tasks-table">
            <thead>
              <tr>
                <th>Task</th>
                <th>Owner</th>
                <th>Due</th>
                <th>Status</th>
                <th>Attached</th>
                {canAct && <th className="actions-col">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) =>
                editing === t.id ? (
                  <EditRow
                    key={t.id}
                    t={t}
                    me={me?.subject}
                    busy={busy}
                    onCancel={() => setEditing(null)}
                    onSave={(patch) => change.mutate({ id: t.id, patch })}
                    columns={canAct ? 6 : 5}
                  />
                ) : (
                  [<tr key={t.id} className={t.done ? "closed-row" : ""}>
                    <td className="task-title">{t.title}</td>
                    <td>
                      {t.assignee ? (
                        <span className="owner" title={t.assignee}>
                          <span className="owner-dot">{initials(t.assignee)}</span>
                          <span className="small">{me && t.assignee === me.subject ? "You" : t.assignee.split("@")[0]}</span>
                        </span>
                      ) : (
                        <span className="muted">–</span>
                      )}
                    </td>
                    <td className="nowrap">
                      {t.due_date ? (
                        !t.done && t.due_date < today() ? (
                          <Chip tone="bad">Overdue · {formatDate(t.due_date)}</Chip>
                        ) : (
                          formatDate(t.due_date)
                        )
                      ) : (
                        <span className="muted">–</span>
                      )}
                    </td>
                    <td>
                      {t.done ? (
                        <Chip>Closed · {STATUS.find((s) => s.value === t.status)?.label}</Chip>
                      ) : (
                        <select
                          className={`status-select st-${t.status}`}
                          value={t.status}
                          disabled={!canAct || busy}
                          onChange={(e) => change.mutate({ id: t.id, patch: { status: e.target.value as TaskStatus } })}
                          aria-label={`Status of ${t.title}`}
                        >
                          {STATUS.map((s) => (
                            <option key={s.value} value={s.value}>
                              {s.label}
                            </option>
                          ))}
                        </select>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="link-btn"
                        aria-expanded={open === t.id}
                        onClick={() => setOpen(open === t.id ? null : t.id)}
                      >
                        {(() => {
                          const docs = detail.documents.filter((x) => x.task_id === t.id).length;
                          const notes = detail.notes.filter((x) => x.task_id === t.id).length;
                          return docs + notes === 0
                            ? "Attach…"
                            : [docs && plural(docs, "file"), notes && plural(notes, "note")].filter(Boolean).join(" · ");
                        })()}
                      </button>
                    </td>
                    {canAct && (
                      <td className="row-actions">
                        {!t.done && (
                          <button type="button" className="btn small" disabled={busy} onClick={() => setEditing(t.id)}>
                            Edit
                          </button>
                        )}
                        <button
                          type="button"
                          className="btn small"
                          disabled={busy}
                          onClick={() => change.mutate({ id: t.id, patch: { done: !t.done } })}
                        >
                          {t.done ? "Reopen" : "Close"}
                        </button>
                        <button
                          type="button"
                          className="icon-btn"
                          title="Delete task"
                          aria-label={`Delete ${t.title}`}
                          disabled={busy}
                          onClick={() => remove.mutate(t.id)}
                        >
                          <Icon name="trash" size={16} />
                        </button>
                      </td>
                    )}
                  </tr>,
                  open === t.id && (
                    <tr key={`${t.id}-items`} className="task-extra">
                      <td colSpan={canAct ? 6 : 5}>
                        <TaskItems caseKey={caseKey} detail={detail} task={t} canAct={canAct} closedCase={closedCase} saved={saved} />
                      </td>
                    </tr>
                  )]
                ),
              )}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

function EditRow({
  t, me, busy, columns, onSave, onCancel,
}: {
  t: CaseTask;
  me: string | undefined;
  busy: boolean;
  columns: number;
  onSave: (patch: Patch) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(t.title);
  const [due, setDue] = useState(t.due_date ?? "");
  const [owner, setOwner] = useState(t.assignee ?? "");
  const others = t.assignee && t.assignee !== me ? t.assignee : null;
  return (
    <tr className="edit-row">
      <td colSpan={columns}>
        <form
          className="task-edit"
          onSubmit={(e) => {
            e.preventDefault();
            if (title.trim()) onSave({ title: title.trim(), due_date: due || null, assignee: owner || null });
          }}
        >
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={255} aria-label="Task" autoFocus />
          <select value={owner} onChange={(e) => setOwner(e.target.value)} aria-label="Owner">
            <option value="">Unassigned</option>
            {me && <option value={me}>Me</option>}
            {others && <option value={others}>{others}</option>}
          </select>
          <input type="date" value={due} onChange={(e) => setDue(e.target.value)} aria-label="Due date" />
          <button type="submit" className="btn primary small" disabled={!title.trim() || busy}>
            Save
          </button>
          <button type="button" className="btn small" onClick={onCancel}>
            Cancel
          </button>
        </form>
      </td>
    </tr>
  );
}


/** What is tagged to one task: its documents and notes, with a way to add more. */
function TaskItems({
  caseKey, detail, task, canAct, closedCase, saved,
}: {
  caseKey: string;
  detail: CaseDetail;
  task: CaseTask;
  canAct: boolean;
  closedCase: boolean;
  saved: (d: CaseDetail) => void;
}) {
  const [, setParams] = useSearchParams();
  const [text, setText] = useState("");
  const docs = detail.documents.filter((d) => d.task_id === task.id);
  const notes = detail.notes.filter((n) => n.task_id === task.id);
  const upload = useMutation({
    mutationFn: (f: File) => api.uploadCaseDocument(caseKey, f, "", task.id),
    onSuccess: saved,
  });
  const note = useMutation({
    mutationFn: () => api.addCaseNote(caseKey, { title: "", body: textToHtml(text), task_id: task.id }),
    onSuccess: (d) => {
      setText("");
      saved(d);
    },
  });
  return (
    <div className="task-items">
      <div>
        <h4>Documents</h4>
        {docs.length === 0 && <p className="muted small">None tagged to this task.</p>}
        <ul className="plain-list">
          {docs.map((d) => (
            <li key={d.id}>
              <a href={api.caseDocumentUrl(caseKey, d.id)} download={d.filename}>
                {d.filename}
              </a>{" "}
              <span className="muted small">{bytes(d.size)}</span>
            </li>
          ))}
        </ul>
        {canAct && (
          <input
            type="file"
            disabled={upload.isPending}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) upload.mutate(f);
              e.target.value = "";
            }}
            aria-label={`Upload a file for ${task.title}`}
          />
        )}
      </div>
      <div>
        <h4>Notes</h4>
        {notes.length === 0 && <p className="muted small">None tagged to this task.</p>}
        <ul className="plain-list">
          {notes.map((n) => (
            <li key={n.id}>
              <button type="button" className="link-btn" onClick={() => setParams({ tab: "notes", note: n.id })}>
                {n.title}
              </button>{" "}
              <span className="muted small">{n.preview.slice(0, 80)}</span>
            </li>
          ))}
        </ul>
        {canAct && !closedCase && (
          <form
            className="note-quick"
            onSubmit={(e) => {
              e.preventDefault();
              if (text.trim()) note.mutate();
            }}
          >
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={2}
              placeholder="Add a note about this task"
              maxLength={4000}
              aria-label={`Note about ${task.title}`}
            />
            <button type="submit" className="btn small" disabled={!text.trim() || note.isPending}>
              Add note
            </button>
          </form>
        )}
      </div>
      {(upload.isError || note.isError) && <ErrorNote error={upload.error ?? note.error} />}
    </div>
  );
}
