import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import type { CaseDetail, CaseStatus } from "../api/types";
import { attrLabel, formatDate, initials, lower, money, plural } from "../lib/friendly";
import { useMe } from "../lib/useMe";
import { Icon } from "../ui/Icon";
import { Chip, ErrorNote, Segmented, Skeleton, Stat, Tabs } from "../ui/kit";
import { ActivityTab } from "./case/ActivityTab";
import { ClaimsTab } from "./case/ClaimsTab";
import { DocumentsTab } from "./case/DocumentsTab";
import { IndicatorsTab } from "./case/IndicatorsTab";
import { NetworkTab } from "./case/NetworkTab";
import { NotesTab } from "./case/NotesTab";
import { PartiesTab } from "./case/PartiesTab";
import { ReportTab } from "./case/ReportTab";
import { isClosed, statusOf, type TabProps } from "./case/shared";
import { TasksTab } from "./case/TasksTab";

type Tab = "indicators" | "network" | "parties" | "claims" | "tasks" | "notes" | "documents" | "activity" | "report";
const TABS: Tab[] = ["indicators", "network", "parties", "claims", "tasks", "notes", "documents", "activity", "report"];

const OBJECTS = new Set(["Claim", "Policy", "Vehicle", "Property"]);
const TYPE_WORDS: Record<string, [string, string]> = {
  Person: ["person", "people"], Organization: ["company", "companies"], Claim: ["claim", "claims"],
  Policy: ["policy", "policies"], Vehicle: ["vehicle", "vehicles"], Property: ["property", "properties"],
  LegalRep: ["attorney", "attorneys"], MedicalProvider: ["medical provider", "medical providers"],
  BodyShop: ["body shop", "body shops"],
};

/** "7 people, 5 claims, 1 attorney" for the entities in a network. */
function typeSummary(types: Record<string, number>): string {
  return Object.entries(types)
    .sort((a, b) => b[1] - a[1])
    .map(([t, n]) => `${n} ${(TYPE_WORDS[t] ?? [t.toLowerCase(), t.toLowerCase()])[n === 1 ? 0 : 1]}`)
    .join(", ");
}

/** One case, worked from tabs: why it was flagged, who is in it, and the work to close it. */
export function CasePage() {
  const { caseKey = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const asked = params.get("tab") as Tab | null;
  const tab: Tab = asked && TABS.includes(asked) ? asked : "indicators";
  const qc = useQueryClient();
  const { me, can } = useMe();
  const detail = useQuery({ queryKey: ["case", caseKey], queryFn: () => api.caseDetail(caseKey) });

  const saved = (d: CaseDetail) => {
    qc.setQueryData(["case", caseKey], d);
    qc.invalidateQueries({ queryKey: ["cases"] });
  };
  const update = useMutation({
    mutationFn: (patch: { status?: CaseStatus; assignee?: string | null }) => api.updateCase(caseKey, patch),
    onSuccess: saved,
  });

  if (detail.isPending) {
    return (
      <div className="case-page">
        <Skeleton rows={8} />
      </div>
    );
  }
  if (detail.isError) {
    return (
      <div className="case-page">
        <BackLink />
        <ErrorNote error={detail.error} />
      </div>
    );
  }

  const d = detail.data;
  const { summary: s } = d;
  const canAct = can("analyst", "steward", "detection_analyst");
  const closed = isClosed(s.status);
  const mine = !!me && s.assignee === me.subject;
  const status = statusOf(s.status);
  const tabProps: TabProps = { caseKey, detail: d, canAct, saved };
  const openTasks = d.tasks.filter((t) => !t.done).length;
  const parties = d.members.filter((m) => !OBJECTS.has(m.entity_type)).length;

  return (
    <div className="case-page">
      <BackLink />
      <header className="case-head">
        <div className="case-title">
          <span className="eyebrow">Case</span>
          <h1>
            {s.focus_label}
            {s.size > 1 && <span className="muted"> + {plural(s.size - 1, "other entity", "other entities")}</span>}
          </h1>
          <p className="muted">
            {typeSummary(s.types)}. Held together by{" "}
            {s.via.map((v) => lower(attrLabel(v))).join(", ") || "nothing shared"}
          </p>
        </div>
        <span className={`risk risk-${s.severity}`} title="Fraud indicators, 0 to 100">
          <b>{s.score}</b>
          {s.severity}
        </span>
      </header>

      <div className="case-workflow">
        <div className="ctl">
          <span className="ctl-label">Status</span>
          {closed ? (
            <>
              <Chip tone={status.tone}>{status.label}</Chip>
              {canAct && (
                <button
                  type="button"
                  className="btn small"
                  disabled={update.isPending}
                  onClick={() => update.mutate({ status: "investigating" })}
                >
                  Reopen
                </button>
              )}
            </>
          ) : canAct ? (
            <Segmented
              label="Case status"
              value={s.status}
              onChange={(v) => update.mutate({ status: v })}
              options={[
                { value: "new", label: "New" },
                { value: "investigating", label: "Investigating" },
              ]}
            />
          ) : (
            <Chip tone={status.tone}>{status.label}</Chip>
          )}
        </div>
        <div className="ctl">
          <span className="ctl-label">Owner</span>
          {s.assignee ? (
            <span className="owner">
              <span className="owner-dot" aria-hidden="true">
                {initials(s.assignee)}
              </span>
              {mine ? "You" : s.assignee}
            </span>
          ) : (
            <span className="muted">Unassigned</span>
          )}
          {canAct && me && (
            <button
              type="button"
              className="btn small"
              disabled={update.isPending}
              onClick={() => update.mutate({ assignee: mine ? null : me.subject })}
            >
              {mine ? "Unassign" : s.assignee ? "Take over" : "Assign to me"}
            </button>
          )}
        </div>
      </div>
      {update.isError && <ErrorNote error={update.error} />}
      {closed && (
        <div className={`note closed-note ${s.status}`}>
          <Icon name="check" size={16} />
          <span>
            Closed as {status.label} on {formatDate(d.closed_at)} by {d.closed_by}. The closing report tab has the
            report.
          </span>
        </div>
      )}

      <div className="stats">
        <Stat value={s.size} label="entities" />
        <Stat value={s.links} label="links" />
        <Stat value={s.claim_count} label="claims" />
        <Stat value={money(s.claimed_amount)} label="claimed" />
      </div>

      <Tabs
        value={tab}
        onChange={(t) => setParams({ tab: t }, { replace: true })}
        tabs={[
          { value: "indicators", label: `Indicators (${d.network.hits.length})` },
          { value: "network", label: "Network" },
          { value: "parties", label: `Parties (${parties})` },
          { value: "claims", label: `Claims (${s.claim_count})` },
          { value: "tasks", label: `Tasks (${openTasks > 0 ? `${openTasks} open` : d.tasks.length})` },
          { value: "notes", label: `Notes (${d.notes.length})` },
          { value: "documents", label: `Documents (${d.documents.length})` },
          { value: "activity", label: `Activity (${d.events.length})` },
          { value: "report", label: "Closing report" },
        ]}
      />
      <div className="case-tab">
        {tab === "indicators" && <IndicatorsTab {...tabProps} />}
        {tab === "network" && <NetworkTab {...tabProps} />}
        {tab === "parties" && <PartiesTab {...tabProps} />}
        {tab === "claims" && <ClaimsTab {...tabProps} />}
        {tab === "tasks" && <TasksTab {...tabProps} />}
        {tab === "notes" && <NotesTab {...tabProps} />}
        {tab === "documents" && <DocumentsTab {...tabProps} />}
        {tab === "activity" && <ActivityTab {...tabProps} />}
        {tab === "report" && <ReportTab {...tabProps} />}
      </div>
    </div>
  );
}

function BackLink() {
  return (
    <Link to="/analytics" className="back-link">
      <Icon name="arrowLeft" size={15} /> All cases
    </Link>
  );
}
