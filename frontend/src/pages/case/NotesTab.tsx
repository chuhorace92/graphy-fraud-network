import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../../api/client";
import type { CaseNote } from "../../api/types";
import { RichEditor } from "../../components/RichEditor";
import { formatDate, plural } from "../../lib/friendly";
import { hasText } from "../../lib/notes";
import { Icon } from "../../ui/Icon";
import { Chip, EmptyState, ErrorNote } from "../../ui/kit";
import { isClosed, type TabProps } from "./shared";

const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const day = (iso: string) => iso.slice(0, 10);

/** The case diary: entries down the left, the selected one on the right. Rich text, editable
 *  until the case is closed. */
export function NotesTab({ caseKey, detail, canAct, saved }: TabProps) {
  const [params] = useSearchParams();
  const closed = isClosed(detail.summary.status);
  const writable = canAct && !closed;
  const notes = useMemo(
    () => [...detail.notes].sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [detail.notes],
  );
  const wanted = params.get("note");
  const [picked, setPicked] = useState<string | null>(wanted);
  const [mode, setMode] = useState<"view" | "new" | "edit">("view");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const selected = notes.find((n) => n.id === picked) ?? (mode === "new" ? undefined : notes[0]);
  const tasks = new Map(detail.tasks.map((t) => [t.id, t.title]));

  useEffect(() => {
    if (wanted) setPicked(wanted);
  }, [wanted]);

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteCaseNote(caseKey, id),
    onSuccess: (d) => {
      setConfirmDelete(false);
      setPicked(null);
      saved(d);
    },
  });

  const groups = useMemo(() => {
    const out: { day: string; items: CaseNote[] }[] = [];
    for (const n of notes) {
      const d = day(n.created_at);
      if (out.at(-1)?.day === d) out.at(-1)!.items.push(n);
      else out.push({ day: d, items: [n] });
    }
    return out;
  }, [notes]);

  return (
    <div className="notes">
      {closed && (
        <div className="note">
          <Icon name="info" size={16} />
          <span>This case is closed, so its notes can be read but not changed. Reopen it to edit them.</span>
        </div>
      )}
      <div className="notes-split">
        <aside className="notes-side" aria-label="Diary entries">
          <div className="notes-side-head">
            <span className="muted small">{plural(notes.length, "entry", "entries")}</span>
            {writable && (
              <button
                type="button"
                className="btn small primary"
                onClick={() => {
                  setMode("new");
                  setPicked(null);
                }}
              >
                <Icon name="plus" size={14} /> New entry
              </button>
            )}
          </div>
          <div className="notes-list">
            {mode === "new" && <div className="note-item active draft">New entry…</div>}
            {groups.map((g) => (
              <section key={g.day}>
                <h4>{formatDate(g.day)}</h4>
                <ul>
                  {g.items.map((n) => (
                    <li key={n.id}>
                      <button
                        type="button"
                        className={`note-item${selected?.id === n.id && mode !== "new" ? " active" : ""}`}
                        onClick={() => {
                          setPicked(n.id);
                          setMode("view");
                          setConfirmDelete(false);
                        }}
                      >
                        <strong>{n.title}</strong>
                        <span className="muted small">
                          {time(n.created_at)}
                          {n.task_id && tasks.get(n.task_id) ? ` · ${tasks.get(n.task_id)}` : ""}
                        </span>
                        <span className="note-preview">{n.preview}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </aside>

        <section className="notes-main" aria-label="Entry">
          {mode === "new" && (
            <NoteForm
              key="new"
              caseKey={caseKey}
              detail={detail}
              onDone={(d, id) => {
                saved(d);
                setPicked(id ?? null);
                setMode("view");
              }}
              onCancel={() => setMode("view")}
            />
          )}
          {mode === "edit" && selected && (
            <NoteForm
              key={selected.id}
              caseKey={caseKey}
              detail={detail}
              note={selected}
              onDone={(d) => {
                saved(d);
                setMode("view");
              }}
              onCancel={() => setMode("view")}
            />
          )}
          {mode === "view" && selected && (
            <article>
              <header className="note-head">
                <div>
                  <h3>{selected.title}</h3>
                  <p className="muted small">
                    {selected.created_by} · {formatDate(selected.created_at)} {time(selected.created_at)}
                    {selected.updated_at && ` · edited ${formatDate(selected.updated_at)} by ${selected.updated_by}`}
                  </p>
                  {selected.task_id && tasks.get(selected.task_id) && (
                    <Chip tone="accent">Task: {tasks.get(selected.task_id)}</Chip>
                  )}
                </div>
                {writable && (
                  <div className="note-actions">
                    <button type="button" className="btn small" onClick={() => setMode("edit")}>
                      Edit
                    </button>
                    {confirmDelete ? (
                      <>
                        <button type="button" className="btn small" onClick={() => setConfirmDelete(false)}>
                          Keep
                        </button>
                        <button
                          type="button"
                          className="btn small danger"
                          disabled={remove.isPending}
                          onClick={() => remove.mutate(selected.id)}
                        >
                          Delete entry
                        </button>
                      </>
                    ) : (
                      <button type="button" className="icon-btn" title="Delete entry" aria-label="Delete entry" onClick={() => setConfirmDelete(true)}>
                        <Icon name="trash" size={16} />
                      </button>
                    )}
                  </div>
                )}
              </header>
              {remove.isError && <ErrorNote error={remove.error} />}
              {/* Stored HTML has been through the server's allow-list sanitizer. */}
              <div className="note-body" dangerouslySetInnerHTML={{ __html: selected.body }} />
            </article>
          )}
          {mode === "view" && !selected && (
            <EmptyState icon="file" title="No entries yet">
              {writable
                ? "Keep a diary of the investigation: calls made, things found, what to do next."
                : "Nothing was written on this case."}
            </EmptyState>
          )}
        </section>
      </div>
    </div>
  );
}

function NoteForm({
  caseKey, detail, note, onDone, onCancel,
}: {
  caseKey: string;
  detail: TabProps["detail"];
  note?: CaseNote;
  onDone: (d: TabProps["detail"], newId?: string) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(note?.title ?? "");
  const [body, setBody] = useState(note?.body ?? "");
  const [task, setTask] = useState(note?.task_id ?? "");
  const save = useMutation({
    mutationFn: async () => {
      if (note) return { d: await api.updateCaseNote(caseKey, note.id, { title, body, task_id: task || null }) };
      const before = new Set(detail.notes.map((n) => n.id));
      const d = await api.addCaseNote(caseKey, { title, body, task_id: task || null });
      return { d, id: d.notes.find((n) => !before.has(n.id))?.id };
    },
    onSuccess: ({ d, id }: { d: TabProps["detail"]; id?: string }) => onDone(d, id),
  });
  const ok = title.trim().length > 0 || hasText(body);
  return (
    <form
      className="note-form-rich"
      onSubmit={(e) => {
        e.preventDefault();
        if (ok) save.mutate();
      }}
    >
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Title (optional: the first line is used)"
        maxLength={255}
        aria-label="Title"
      />
      <label className="check">
        <span className="muted small">About task</span>
        <select value={task} onChange={(e) => setTask(e.target.value)} aria-label="Tag to a task">
          <option value="">None</option>
          {detail.tasks.map((t) => (
            <option key={t.id} value={t.id}>
              {t.title}
            </option>
          ))}
        </select>
      </label>
      <RichEditor value={body} onChange={setBody} />
      {save.isError && <ErrorNote error={save.error} />}
      <div className="form-actions">
        <button type="submit" className="btn primary" disabled={!ok || save.isPending}>
          {note ? "Save changes" : "Save entry"}
        </button>
        <button type="button" className="btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
