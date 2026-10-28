import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/client";
import type { Authority, Outcome, ReportDraft } from "../../api/types";
import { formatDate, money, plural } from "../../lib/friendly";
import { Icon } from "../../ui/Icon";
import { Chip, ErrorNote, Stat } from "../../ui/kit";
import { isClosed, OUTCOMES, statusOf, type TabProps } from "./shared";

const NO_AUTHORITY: Authority = { reported: false, name: "", reference: "", reported_on: null, notes: "" };
const AUTHORITIES = [
  "State insurance department",
  "State fraud bureau",
  "National Insurance Crime Bureau",
  "Law enforcement",
];

/** Closes the case: an outcome, what was found, what should happen next, and whether it was
 *  reported to an authority. */
export function ReportTab(p: TabProps) {
  const { detail } = p;
  return isClosed(detail.summary.status) ? <FinalReport {...p} /> : <ReportForm {...p} />;
}

function Facts({ detail }: Pick<TabProps, "detail">) {
  const s = detail.summary;
  const done = detail.tasks.filter((t) => t.done).length;
  return (
    <div className="stats">
      <Stat value={s.size} label="entities" />
      <Stat value={s.claim_count} label="claims" />
      <Stat value={money(s.claimed_amount)} label="claimed" />
      <Stat value={`${s.score} · ${s.severity}`} label="fraud score" />
      <Stat value={`${done}/${detail.tasks.length}`} label="tasks closed" />
      <Stat value={detail.documents.length} label="documents" />
    </div>
  );
}

function ReportForm({ caseKey, detail, canAct, saved }: TabProps) {
  const draft = detail.report;
  const [outcome, setOutcome] = useState<Outcome | null>(draft?.outcome ?? null);
  const [summary, setSummary] = useState(draft?.summary ?? "");
  const [recommendation, setRecommendation] = useState(draft?.recommendation ?? "");
  const [recovered, setRecovered] = useState(draft?.amount_recovered?.toString() ?? "");
  const [authority, setAuthority] = useState<Authority>(draft?.authority ?? NO_AUTHORITY);
  const [confirming, setConfirming] = useState(false);
  const [drafted, setDrafted] = useState<ReportDraft | null>(null);
  const agent = useQuery({ queryKey: ["agent-status"], queryFn: api.agentStatus, staleTime: Infinity });
  const agentDraft = useMutation({
    mutationFn: () => api.draftReport(caseKey),
    onSuccess: (d) => {
      setOutcome(d.outcome);
      setSummary(d.summary);
      setRecommendation(d.recommendation);
      setRecovered(d.amount_recovered?.toString() ?? "");
      setDrafted(d);
    },
  });
  const runAgent = () => {
    const written = summary.trim() || recommendation.trim();
    if (!written || window.confirm("The agent's draft will replace what you have written here. Continue?")) {
      agentDraft.mutate();
    }
  };

  const amount = outcome === "confirmed" && recovered.trim() !== "" ? Number(recovered) : null;
  const badAmount = amount !== null && (!Number.isFinite(amount) || amount < 0);
  const save = useMutation({
    mutationFn: () =>
      api.saveCaseReport(caseKey, {
        outcome, summary, recommendation, amount_recovered: badAmount ? null : amount, authority: cleanAuthority(authority),
      }),
    onSuccess: saved,
  });
  const close = useMutation({
    mutationFn: () =>
      api.closeCase(caseKey, {
        outcome: outcome!, summary: summary.trim(), recommendation, amount_recovered: amount,
        authority: cleanAuthority(authority),
      }),
    onSuccess: (d) => {
      setConfirming(false);
      saved(d);
    },
  });
  const openTasks = detail.tasks.filter((t) => !t.done).length;
  const ready = !!outcome && summary.trim().length > 0 && !badAmount && (!authority.reported || !!authority.name.trim());

  return (
    <div className="report">
      <Facts detail={detail} />
      <div className="checklist">
        <span className={detail.documents.length ? "ok" : "todo"}>
          <Icon name={detail.documents.length ? "check" : "alert"} size={14} />
          {detail.documents.length ? `${plural(detail.documents.length, "document")} attached` : "No documents attached"}
        </span>
        <span className={openTasks ? "todo" : "ok"}>
          <Icon name={openTasks ? "alert" : "check"} size={14} />
          {openTasks ? `${plural(openTasks, "task")} still open` : "All tasks closed"}
        </span>
      </div>

      {canAct && (
        <section className="agent-panel" aria-label="Agent mode">
          <div className="agent-head">
            <div>
              <h4>
                <Icon name="play" size={14} /> Agent mode
              </h4>
              <p className="muted small">
                Reads this case's {plural(detail.notes.length, "note")} and {plural(detail.documents.length, "document")}{" "}
                and drafts the outcome, summary and recommendation below. Nothing is saved until you save a draft or
                close the case, and the case is never closed for you. What it reads is sent to Claude.
              </p>
            </div>
            <button
              type="button"
              className="btn"
              disabled={!agent.data?.enabled || agentDraft.isPending}
              title={agent.data && !agent.data.enabled ? "Agent mode is off: set an Anthropic API key" : undefined}
              onClick={runAgent}
            >
              {agentDraft.isPending ? "Reading the case…" : drafted ? "Draft again" : "Draft with agent"}
            </button>
          </div>
          {agent.data && !agent.data.enabled && (
            <p className="muted small">
              Agent mode is off. Set <code>ANTHROPIC_API_KEY</code> for the API to turn it on.
            </p>
          )}
          {agentDraft.isError && <ErrorNote error={agentDraft.error} />}
          {drafted && (
            <div className="agent-result">
              <p className="small">
                Drafted from {plural(drafted.used_documents.length, "document")} and {plural(drafted.used_notes, "note")} with{" "}
                {drafted.model}. <strong>Read it and edit it before you close the case.</strong>
                {drafted.outcome === null && " The material did not settle the outcome, so none is chosen."}
              </p>
              {drafted.caveats.length > 0 && (
                <ul className="caveats">
                  {drafted.caveats.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>
      )}

      <fieldset className="outcomes" disabled={!canAct}>
        <legend>Outcome</legend>
        {OUTCOMES.map((o) => (
          <label key={o.value} className={`outcome${outcome === o.value ? " on" : ""}`}>
            <input type="radio" name="outcome" checked={outcome === o.value} onChange={() => setOutcome(o.value)} />
            <strong>{o.label}</strong>
            <span className="muted small">{o.hint}</span>
          </label>
        ))}
      </fieldset>

      <label className="field">
        <span>Summary of findings</span>
        <textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          rows={6}
          maxLength={8000}
          disabled={!canAct}
          placeholder="What was investigated, what the evidence shows, and why you reached this outcome."
        />
      </label>
      <label className="field">
        <span>Recommendation</span>
        <textarea
          value={recommendation}
          onChange={(e) => setRecommendation(e.target.value)}
          rows={3}
          maxLength={4000}
          disabled={!canAct}
          placeholder="Next steps: deny or pay claims, refer to SIU, report to an authority, recover funds, monitor…"
        />
      </label>
      {outcome === "confirmed" && (
        <label className="field narrow">
          <span>Amount recovered or saved (USD)</span>
          <input
            inputMode="decimal"
            value={recovered}
            onChange={(e) => setRecovered(e.target.value)}
            disabled={!canAct}
            placeholder="0"
          />
          {badAmount && <span className="field-error">Enter a number of zero or more.</span>}
        </label>
      )}

      <fieldset className="authority" disabled={!canAct}>
        <legend>Reported to authority</legend>
        <label className="check">
          <input
            type="checkbox"
            checked={authority.reported}
            onChange={(e) => setAuthority({ ...authority, reported: e.target.checked })}
          />
          <span>
            <strong>This case was reported to an authority</strong>
            <small>For example a fraud bureau, the insurance department or law enforcement.</small>
          </span>
        </label>
        {authority.reported && (
          <div className="authority-fields">
            <label className="field">
              <span>Authority</span>
              <input
                list="authorities"
                value={authority.name}
                onChange={(e) => setAuthority({ ...authority, name: e.target.value })}
                maxLength={255}
                placeholder="Who it was reported to"
              />
              <datalist id="authorities">
                {AUTHORITIES.map((a) => (
                  <option key={a} value={a} />
                ))}
              </datalist>
            </label>
            <label className="field">
              <span>Reference number</span>
              <input
                value={authority.reference}
                onChange={(e) => setAuthority({ ...authority, reference: e.target.value })}
                maxLength={255}
                placeholder="Their case or report number"
              />
            </label>
            <label className="field">
              <span>Date reported</span>
              <input
                type="date"
                value={authority.reported_on ?? ""}
                onChange={(e) => setAuthority({ ...authority, reported_on: e.target.value || null })}
              />
            </label>
            <label className="field wide-field">
              <span>Notes</span>
              <textarea
                value={authority.notes}
                onChange={(e) => setAuthority({ ...authority, notes: e.target.value })}
                rows={3}
                maxLength={4000}
                placeholder="What was sent, who you spoke to, what they said, what happens next"
              />
            </label>
          </div>
        )}
      </fieldset>

      {(save.isError || close.isError) && <ErrorNote error={save.error ?? close.error} />}
      {canAct && !confirming && (
        <div className="report-actions">
          <button type="button" className="btn" disabled={save.isPending || badAmount} onClick={() => save.mutate()}>
            {save.isSuccess && !save.isPending ? "Draft saved" : "Save draft"}
          </button>
          <button type="button" className="btn primary" disabled={!ready} onClick={() => setConfirming(true)}>
            Close case…
          </button>
          {!ready && (
            <span className="muted small">
              Choose an outcome and write a summary to close
              {authority.reported && !authority.name.trim() ? ", and say who it was reported to" : ""}.
            </span>
          )}
        </div>
      )}
      {canAct && confirming && outcome && (
        <div className="confirm-bar" role="alertdialog" aria-label="Confirm closing the case">
          <span>
            Close this case as <strong>{statusOf(outcome).label}</strong>?
            {openTasks > 0 && <> {plural(openTasks, "task")} will stay open.</>} You can reopen it later.
          </span>
          <button type="button" className="btn" onClick={() => setConfirming(false)}>
            Cancel
          </button>
          <button type="button" className="btn primary" disabled={close.isPending} onClick={() => close.mutate()}>
            Close case
          </button>
        </div>
      )}
    </div>
  );
}

function FinalReport({ detail }: Pick<TabProps, "detail">) {
  const { summary: s, report: r } = detail;
  const status = statusOf(s.status);
  return (
    <article className="report final">
      <header className="report-head">
        <div>
          <span className="eyebrow">Closing report</span>
          <h3>{s.focus_label}{s.size > 1 && ` + ${plural(s.size - 1, "other entity", "other entities")}`}</h3>
          <p className="muted small">
            Closed {formatDate(detail.closed_at)} by {detail.closed_by}
          </p>
        </div>
        <div className="report-head-end">
          <Chip tone={status.tone}>{status.label}</Chip>
          <button type="button" className="btn small no-print" onClick={() => window.print()}>
            Print
          </button>
        </div>
      </header>
      <Facts detail={detail} />
      {r?.outcome === "confirmed" && r.amount_recovered != null && (
        <p>
          <strong>Recovered:</strong> {money(r.amount_recovered, true)}
        </p>
      )}
      <h4>Summary of findings</h4>
      <p className="prewrap">{r?.summary}</p>
      {r?.recommendation && (
        <>
          <h4>Recommendation</h4>
          <p className="prewrap">{r.recommendation}</p>
        </>
      )}
      <h4>Reported to authority</h4>
      {r?.authority?.reported ? (
        <div className="prewrap">
          <strong>{r.authority.name}</strong>
          {r.authority.reference && <> · reference {r.authority.reference}</>}
          {r.authority.reported_on && <> · {formatDate(r.authority.reported_on)}</>}
          {r.authority.notes && <p>{r.authority.notes}</p>}
        </div>
      ) : (
        <p className="muted">Not reported to an authority.</p>
      )}
      {detail.documents.length > 0 && (
        <>
          <h4>Documents</h4>
          <ul className="plain">
            {detail.documents.map((d) => (
              <li key={d.id}>
                <strong>{d.filename}</strong>
                {d.note && <> — {d.note}</>}
              </li>
            ))}
          </ul>
        </>
      )}
    </article>
  );
}

/** What is sent for the authority section: nothing but the flag when it was not reported. */
function cleanAuthority(a: Authority): Authority {
  return a.reported ? { ...a, name: a.name.trim(), reference: a.reference.trim() } : { ...NO_AUTHORITY };
}
