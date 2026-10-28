import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { AnalyticsRule, RuleCondition, RuleDocument, RulePreview } from "../api/types";
import { plural } from "../lib/friendly";
import { Icon } from "../ui/Icon";
import { Chip, EmptyState, ErrorNote, Skeleton } from "../ui/kit";

/** What the engine can measure on a network today. Anything else waits for the Phase 2 run. */
const METRICS: { value: string; label: string; help: string }[] = [
  { value: "shared_value_holders", label: "Parties sharing one attribute",
    help: "The most parties that hold the same phone, address, account or device." },
  { value: "provider_pair_claims", label: "Two provider types together on claims",
    help: "Claims where one provider of each chosen type appear together." },
  { value: "recurring_group_size", label: "Same group on auto claims, shifting roles",
    help: "People who keep turning up on the same auto claims and change roles between them." },
  { value: "repeat_claim_participants", label: "The same person on several claims",
    help: "The most claims one person is on, in any role." },
  { value: "alias_pairs", label: "Probable aliases",
    help: "Links between records that look like the same person under another name or ID." },
  { value: "claims_in_window", label: "Claims bunched in time",
    help: "The most claims filed within a number of days of each other." },
  { value: "claims_after_policy_start", label: "Claims soon after a policy started",
    help: "Claims filed within a number of days of their policy starting." },
];
const PROVIDERS = [
  { value: "MedicalProvider", label: "Medical provider" },
  { value: "LegalRep", label: "Legal representative" },
  { value: "BodyShop", label: "Auto body shop" },
];
const ATTRIBUTES = ["address", "phone", "email", "bank_acct", "device", "tax_id"];
const ID_PATTERN = /^[a-z0-9][a-z0-9_-]{1,127}$/;
const OPS = [">=", ">", "<=", "<", "=="] as const;

const blank = (): RuleDocument => ({
  rule_id: "", scope: "cluster", severity: "medium", description: "",
  conditions: [{ metric: "shared_value_holders", op: ">=", value: 2 }],
});

const stateTone = { published: "good", draft: "accent", retired: "neutral" } as const;
const stateLabel = (s: string) => (s === "published" ? "Live" : s === "draft" ? "Draft" : "Retired");

/** The version a rule is known by: the live one, else the newest. */
function current(versions: AnalyticsRule[]): AnalyticsRule {
  return versions.find((v) => v.state === "published") ?? versions[0];
}

export function RulesPage() {
  const qc = useQueryClient();
  const rules = useQuery({ queryKey: ["analytics-rules"], queryFn: api.analyticsRules });
  const [selected, setSelected] = useState<string | "new" | null>(null);

  const groups = useMemo(() => {
    const by = new Map<string, AnalyticsRule[]>();
    for (const r of rules.data ?? []) by.set(r.rule_id, [...(by.get(r.rule_id) ?? []), r]);
    for (const v of by.values()) v.sort((a, b) => b.version - a.version);
    return by;
  }, [rules.data]);

  useEffect(() => {
    if (selected === null && groups.size > 0) setSelected([...groups.keys()][0]);
  }, [groups, selected]);

  // A change can alter every network's score, so everything derived from the rules refreshes.
  const refresh = () => {
    for (const key of ["analytics-rules", "networks", "entity-network"]) {
      qc.invalidateQueries({ queryKey: [key] });
    }
  };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Rule library</h1>
          <p className="muted">
            The detection rules behind the fraud indicators. Edit a rule to save a new version, test
            it on today's data, then publish it. Earlier versions are kept and can be restored.
          </p>
        </div>
        <button type="button" className="btn primary" onClick={() => setSelected("new")}>
          <Icon name="plus" size={16} /> New rule
        </button>
      </header>

      {rules.isPending && <Skeleton rows={5} />}
      {rules.isError && <ErrorNote error={rules.error} />}
      {rules.isSuccess && groups.size === 0 && selected !== "new" && (
        <EmptyState icon="rules" title="No rules yet">
          Start the stack with <code>make up</code> to store the default rules, or create one here.
        </EmptyState>
      )}

      {rules.isSuccess && (
        <div className="rules-layout">
          <ul className="rule-index">
            {[...groups.entries()].map(([id, versions]) => {
              const cur = current(versions);
              return (
                <li key={id}>
                  <button type="button" className={selected === id ? "on" : ""} onClick={() => setSelected(id)}>
                    <span className="rule-title">{cur.document.description || id}</span>
                    <span className="rule-meta">
                      <Chip tone={stateTone[cur.state as keyof typeof stateTone] ?? "neutral"}>
                        {stateLabel(cur.state)} v{cur.version}
                      </Chip>
                      <span className={`risk risk-${cur.document.severity}`}>{cur.document.severity}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>

          {selected && (
            <RuleEditor
              key={selected}
              ruleId={selected === "new" ? null : selected}
              versions={selected === "new" ? [] : (groups.get(selected) ?? [])}
              onChanged={refresh}
              onCreated={(id) => setSelected(id)}
              onDeleted={() => setSelected(null)}
            />
          )}
        </div>
      )}
    </div>
  );
}

function RuleEditor(p: {
  ruleId: string | null;
  versions: AnalyticsRule[];
  onChanged: () => void;
  onCreated: (ruleId: string) => void;
  onDeleted: () => void;
}) {
  const start = p.versions.length ? current(p.versions) : null;
  const [loaded, setLoaded] = useState<AnalyticsRule | null>(start);
  const [doc, setDoc] = useState<RuleDocument>(start ? structuredClone(start.document) : blank());
  const [preview, setPreview] = useState<RulePreview | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const edit = (patch: Partial<RuleDocument>) => {
    setDoc((d) => ({ ...d, ...patch }));
    setPreview(null);
  };
  const setCond = (i: number, patch: Partial<RuleCondition>) =>
    edit({ conditions: doc.conditions.map((c, j) => (j === i ? { ...c, ...patch } : c)) });

  const save = useMutation({
    mutationFn: () => api.createAnalyticsRule(clean(doc)),
    onSuccess: (r) => {
      setMessage(`Saved as draft v${r.version}. Publish it to make it live.`);
      p.onChanged();
      p.onCreated(r.rule_id);
    },
  });
  const test = useMutation({ mutationFn: () => api.previewAnalyticsRule(clean(doc)), onSuccess: setPreview });
  const act = useMutation({
    mutationFn: async (a: { kind: "publish" | "retire" | "delete"; id: string }) => {
      if (a.kind === "publish") await api.publishAnalyticsRule(a.id);
      else if (a.kind === "retire") await api.retireAnalyticsRule(a.id);
      else await api.deleteAnalyticsRule(a.id);
    },
    onSuccess: (_, a) => {
      setMessage(a.kind === "publish" ? "Published. Network scores now use this version."
        : a.kind === "retire" ? "Retired. The rule no longer adds to any score." : "Draft deleted.");
      p.onChanged();
      if (a.kind === "delete" && p.versions.length <= 1) p.onDeleted();
    },
  });

  const idOk = p.ruleId !== null || ID_PATTERN.test(doc.rule_id);
  const ready = idOk && doc.conditions.length > 0;
  const error = save.error ?? test.error ?? act.error;

  return (
    <section className="rule-editor">
      <h2>{p.ruleId ?? "New rule"}</h2>
      {loaded && (
        <p className="muted small">
          Editing a copy of v{loaded.version} ({stateLabel(loaded.state).toLowerCase()}). Saving creates a new
          draft; nothing changes until you publish.
        </p>
      )}

      {p.ruleId === null && (
        <Field label="Rule id" hint="Lowercase letters, digits, - and _. Cannot be changed later.">
          <input value={doc.rule_id} onChange={(e) => edit({ rule_id: e.target.value })} placeholder="e.g. clinic-and-shop-on-three-claims" />
        </Field>
      )}
      <Field label="What it looks for">
        <textarea rows={2} value={doc.description ?? ""} onChange={(e) => edit({ description: e.target.value })} />
      </Field>
      <Field label="Severity" hint="Adds 5, 15 or 25 points to a network's score when the rule fires, unless you set the points below.">
        <select value={doc.severity} onChange={(e) => edit({ severity: e.target.value as RuleDocument["severity"] })}>
          <option value="low">Low (+5)</option>
          <option value="medium">Medium (+15)</option>
          <option value="high">High (+25)</option>
        </select>
      </Field>
      <Field label="Points" hint="What the rule adds to the score (which tops out at 100). Leave blank to use the severity's points.">
        <input
          type="number" min={1} max={50} placeholder="by severity" value={doc.points ?? ""}
          onChange={(e) => edit({ points: e.target.value ? Math.max(1, Math.min(50, Number(e.target.value))) : null })}
        />
      </Field>
      <Field label="Points for each" hint="Optional. Add this many points for each person, claim or pair the rule names, up to the points above.">
        <input
          type="number" min={1} max={50} placeholder="a flat amount" value={doc.points_each ?? ""}
          onChange={(e) => edit({ points_each: e.target.value ? Math.max(1, Math.min(50, Number(e.target.value))) : null })}
        />
      </Field>

      <h3>Fires when all of these hold</h3>
      {doc.conditions.map((c, i) => (
        <div className="cond" key={i}>
          <select value={c.metric} onChange={(e) => setCond(i, { metric: e.target.value, types: null, attr_type: null, min_claims: null, window_days: null })}>
            {METRICS.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
          <span className="muted small">{METRICS.find((m) => m.value === c.metric)?.help}</span>
          <div className="cond-args">
            {c.metric === "provider_pair_claims" && (
              <>
                <ProviderSelect value={c.types?.[0] ?? "MedicalProvider"} onChange={(v) => setCond(i, { types: [v, c.types?.[1] ?? "LegalRep"] })} />
                <span>and</span>
                <ProviderSelect value={c.types?.[1] ?? "LegalRep"} onChange={(v) => setCond(i, { types: [c.types?.[0] ?? "MedicalProvider", v] })} />
              </>
            )}
            {c.metric === "shared_value_holders" && (
              <select value={c.attr_type ?? ""} onChange={(e) => setCond(i, { attr_type: e.target.value || null })}>
                <option value="">any attribute</option>
                {ATTRIBUTES.map((a) => (
                  <option key={a} value={a}>{a.replace("_", " ")}</option>
                ))}
              </select>
            )}
            {c.metric === "recurring_group_size" && (
              <label className="inline">
                on at least
                <input type="number" min={2} value={c.min_claims ?? 2} onChange={(e) => setCond(i, { min_claims: Number(e.target.value) })} />
                shared claims
              </label>
            )}
            {(c.metric === "claims_in_window" || c.metric === "claims_after_policy_start") && (
              <label className="inline">
                within
                <input
                  type="number" min={1} max={3650} value={c.window_days ?? (c.metric === "claims_in_window" ? 120 : 60)}
                  onChange={(e) => setCond(i, { window_days: Number(e.target.value) })}
                />
                days
              </label>
            )}
            <span>is</span>
            <select value={c.op} onChange={(e) => setCond(i, { op: e.target.value as RuleCondition["op"] })}>
              {OPS.map((o) => (
                <option key={o}>{o}</option>
              ))}
            </select>
            <input type="number" min={0} value={c.value} onChange={(e) => setCond(i, { value: Number(e.target.value) })} />
            {doc.conditions.length > 1 && (
              <button type="button" className="btn small" onClick={() => edit({ conditions: doc.conditions.filter((_, j) => j !== i) })}>
                Remove
              </button>
            )}
          </div>
        </div>
      ))}
      <button type="button" className="btn small" onClick={() => edit({ conditions: [...doc.conditions, { metric: "shared_value_holders", op: ">=", value: 2 }] })}>
        <Icon name="plus" size={14} /> Add condition
      </button>

      <div className="rule-actions">
        <button type="button" className="btn" disabled={!ready || test.isPending} onClick={() => test.mutate()}>
          <Icon name="play" size={14} /> {test.isPending ? "Testing…" : "Test on current data"}
        </button>
        <button type="button" className="btn primary" disabled={!ready || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Saving…" : "Save as new draft"}
        </button>
      </div>

      {error && <ErrorNote error={error} />}
      {message && !error && <div className="note"><Icon name="check" size={16} /><span>{message}</span></div>}
      {preview && <PreviewResult result={preview} />}

      {p.versions.length > 0 && (
        <>
          <h3>Versions</h3>
          <ol className="versions">
            {p.versions.map((v) => (
              <li key={v.id} className={loaded?.id === v.id ? "on" : ""}>
                <span>
                  <strong>v{v.version}</strong>{" "}
                  <Chip tone={stateTone[v.state as keyof typeof stateTone] ?? "neutral"}>{stateLabel(v.state)}</Chip>
                </span>
                <span className="muted small">
                  {v.created_by} · {new Date(v.created_at).toLocaleDateString()} · {v.document.severity}
                </span>
                <span className="version-actions">
                  <button type="button" className="btn small" onClick={() => { setLoaded(v); setDoc(structuredClone(v.document)); setPreview(null); }}>
                    Edit a copy
                  </button>
                  {v.state !== "published" && (
                    <button type="button" className="btn small" disabled={act.isPending} onClick={() => act.mutate({ kind: "publish", id: v.id })}>
                      {v.state === "retired" ? "Restore" : "Publish"}
                    </button>
                  )}
                  {v.state === "published" && (
                    <button type="button" className="btn small" disabled={act.isPending} onClick={() => act.mutate({ kind: "retire", id: v.id })}>
                      Retire
                    </button>
                  )}
                  {v.state === "draft" && (
                    <button type="button" className="btn small" disabled={act.isPending} onClick={() => act.mutate({ kind: "delete", id: v.id })}>
                      Delete
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}

/** Drop the arguments that do not belong to the chosen metric before saving. */
function clean(doc: RuleDocument): RuleDocument {
  return {
    ...doc,
    description: doc.description?.trim() || null,
    points: doc.points || null,
    points_each: doc.points_each || null,
    conditions: doc.conditions.map((c) => ({
      metric: c.metric, op: c.op, value: c.value,
      attr_type: c.metric === "shared_value_holders" ? c.attr_type || null : null,
      types: c.metric === "provider_pair_claims" ? (c.types ?? ["MedicalProvider", "LegalRep"]) : null,
      min_claims: c.metric === "recurring_group_size" ? (c.min_claims ?? 2) : null,
      window_days:
        c.metric === "claims_in_window" ? (c.window_days ?? 120)
          : c.metric === "claims_after_policy_start" ? (c.window_days ?? 60) : null,
    })),
  };
}

function PreviewResult({ result }: { result: RulePreview }) {
  return (
    <div className="preview">
      <strong>
        Would fire on {result.networks_hit} of {plural(result.networks_checked, "network")}
      </strong>
      {result.examples.length === 0 ? (
        <p className="muted small">No network matches today. Loosen a threshold to see examples.</p>
      ) : (
        <ul>
          {result.examples.map((e) => (
            <li key={e.network_id}>
              <span>{e.detail}</span>
              <span className="muted small">
                {plural(e.size, "entity", "entities")} · around {e.focus_label}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <em className="muted small">{hint}</em>}
    </label>
  );
}

function ProviderSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      {PROVIDERS.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}
