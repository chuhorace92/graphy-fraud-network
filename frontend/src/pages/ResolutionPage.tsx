import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { AttributeScoring, ErType, Job, ReviewPair, RuleDoc, RuleSet, Strength } from "../api/types";
import { attrLabel, plural, relativeTime } from "../lib/friendly";
import { useMe } from "../lib/useMe";
import { Icon } from "../ui/Icon";
import { Chip, EmptyState, ErrorNote, Segmented, Skeleton } from "../ui/kit";

const TYPES: { value: ErType; label: string }[] = [
  { value: "Person", label: "People" },
  { value: "Organization", label: "Companies" },
  { value: "Vehicle", label: "Vehicles" },
  { value: "LegalRep", label: "Attorneys" },
  { value: "MedicalProvider", label: "Medical providers" },
  { value: "BodyShop", label: "Body shops" },
];
const TYPE_LABEL = Object.fromEntries(TYPES.map((t) => [t.value, t.label]));

type Compare = AttributeScoring["compare"];

/** What each attribute is for, and which ways of comparing it make sense. */
const ATTRIBUTES: Record<string, { hint: string; compares: Compare[] }> = {
  tax_id: { hint: "The same person or company under one ID. Two different IDs on the same name usually mean two people.", compares: ["exact"] },
  name: { hint: "Same or similar name. For a person: the surname, the first name (with nicknames and initials), ignoring a middle name.", compares: ["exact", "fuzzy", "name_parts"] },
  dob: { hint: "The same date of birth, or just the same year.", compares: ["exact", "year"] },
  incorporation_date: { hint: "The same date of incorporation, or just the same year.", compares: ["exact", "year"] },
  email: { hint: "One mailbox behind two records is strong; it can merge them on its own.", compares: ["exact"] },
  phone: { hint: "Often a shared switchboard; ignore it when too many records use it.", compares: ["exact"] },
  address: { hint: "Households and buildings share addresses innocently; keep it low.", compares: ["exact", "fuzzy"] },
  device: { hint: "The same device or IP address.", compares: ["exact"] },
  bank_acct: { hint: "Shared accounts are what rings look like. They add to a score but should not merge on their own.", compares: ["exact"] },
  vin: { hint: "The same vehicle identification number: the same vehicle.", compares: ["exact"] },
  plate_number: { hint: "The same plate; plates are reused, so it is weaker than the VIN.", compares: ["exact"] },
};
const COMPARE_LABEL: Record<Compare, string> = {
  exact: "Exact match", fuzzy: "Fuzzy match", name_parts: "By name parts", year: "Same year",
};

const STRENGTHS: { value: Strength; label: string; hint: string }[] = [
  { value: "off", label: "Off", hint: "Not used to score" },
  { value: "low", label: "Low", hint: "A weak indicator" },
  { value: "medium", label: "Medium", hint: "A moderate indicator" },
  { value: "strong", label: "Strong", hint: "A strong indicator" },
];

const STALL_AFTER_MS = 30 * 60 * 1000;

/** A job that has sat "queued" or "running" this long almost certainly died; say so rather than
 *  showing it as busy forever (and blocking the Run button). */
function effectiveStatus(job: Job): Job["status"] | "stalled" {
  const active = job.status === "queued" || job.status === "running";
  return active && Date.now() - new Date(job.created_at).getTime() > STALL_AFTER_MS ? "stalled" : job.status;
}

function runSummary(job: Job): string {
  if (job.error) return job.error;
  type Counts = { records?: number; entities?: number; merged_records?: number; pairs_review?: number };
  const all = Object.values(job.counts).filter((c): c is Counts => typeof c === "object" && c !== null && "records" in c);
  const records = all.reduce((t, c) => t + (c.records ?? 0), 0);
  if (!records) return job.status === "succeeded" ? "Nothing to resolve" : "";
  const merged = all.reduce((t, c) => t + (c.merged_records ?? 0), 0);
  const review = all.reduce((t, c) => t + (c.pairs_review ?? 0), 0);
  return `${plural(all.reduce((t, c) => t + (c.entities ?? 0), 0), "entity", "entities")} from ${plural(records, "record")}` +
    `${merged ? `, ${plural(merged, "record")} merged` : ""}${review ? `, ${plural(review, "pair")} to review` : ""}`;
}

function triggerLabel(j: Job): string {
  const t = String(j.params.trigger ?? "");
  if (t.startsWith("batch:")) return "A data upload";
  if (t === "schedule") return "The nightly schedule";
  if (t.startsWith("rule_set.")) return "A rule change";
  return j.created_by === "system" ? "The system" : j.created_by;
}

type Doc = { scoring?: RuleDoc["scoring"]; deterministic_rules?: { attrs: string[] }[] };

/** One line for a rule set in the versions table. */
function describe(doc: Doc): string {
  const s = doc.scoring;
  if (!s) {
    const keys = (doc.deterministic_rules ?? []).map((r) => r.attrs.map((a) => attrLabel(a)).join(" + "));
    return keys.length ? `Merges records with the same ${keys.join(" or ").toLowerCase()}.` : "No automatic merging.";
  }
  const alone = Object.entries(s.attributes).filter(([, a]) => a.merge_alone).map(([k]) => attrLabel(k));
  const score = s.merge_by_score ? `merges at ${s.auto_merge}+, ` : "";
  const used = Object.entries(s.attributes).filter(([, a]) => a.strength !== "off").length;
  return (
    `Scores ${plural(used, "attribute")}: ${score}reviews at ${s.review}+` +
    (alone.length ? `; ${alone.join(", ")} merges on its own` : "") +
    "."
  );
}

export function ResolutionPage() {
  const qc = useQueryClient();
  const { can } = useMe();
  const steward = can("steward");
  const denied = steward ? undefined : "Requires the steward role";
  const [type, setType] = useState<ErType>("Person");
  const active = useQuery({ queryKey: ["resolution-active", type], queryFn: () => api.activeRules(type) });
  const ruleSets = useQuery({ queryKey: ["rule-sets"], queryFn: api.ruleSets });
  const jobs = useQuery({ queryKey: ["jobs", "resolution"], queryFn: () => api.jobs("resolution"), refetchInterval: 5000 });
  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ["jobs"] }),
      qc.invalidateQueries({ queryKey: ["rule-sets"] }),
      qc.invalidateQueries({ queryKey: ["resolution-active"] }),
      qc.invalidateQueries({ queryKey: ["review-queue"] }),
    ]);
  const publish = useMutation({ mutationFn: api.publishRuleSet, onSuccess: refresh });
  const rollback = useMutation({ mutationFn: api.rollbackRuleSet, onSuccess: refresh });
  const run = useMutation({ mutationFn: api.runResolution, onSuccess: refresh });
  const running = jobs.data?.some((j) => ["queued", "running"].includes(effectiveStatus(j)));

  return (
    <div className="page wide">
      <header className="page-head">
        <div>
          <h1>Entity resolution</h1>
          <p className="muted">
            Decide which records are the same real person, company or vehicle. Each detail is a lever; together they make a score.
            Pairs that score in the review band are drawn on the graph as probable aliases and queued for a decision.
          </p>
        </div>
        <button
          type="button"
          className="btn primary"
          disabled={!steward || run.isPending || running}
          title={denied}
          onClick={() => run.mutate()}
        >
          <Icon name="play" size={15} /> {running ? "Running…" : "Run now"}
        </button>
      </header>
      {[publish, rollback, run].map((m, i) => m.isError && <ErrorNote key={i} error={m.error} />)}

      {active.isPending && <Skeleton rows={6} />}
      {active.isError && <ErrorNote error={active.error} />}
      <div className="ctl type-pick">
        <span className="ctl-label">Controls for</span>
        <Segmented label="Entity type" value={type} onChange={setType} options={TYPES} />
      </div>
      {active.data && (
        <Controls key={`${type}-${active.data.name}-${active.data.version}`} entityType={type} active={active.data} steward={steward} onSaved={refresh} />
      )}

      <ReviewQueue steward={steward} onRun={() => run.mutate()} running={!!running} />

      <section className="page-section">
        <h2>Rule versions</h2>
        {ruleSets.isPending && <Skeleton rows={3} />}
        {ruleSets.isError && <ErrorNote error={ruleSets.error} />}
        {ruleSets.data?.length === 0 && (
          <p className="muted">No versions yet, so the built-in defaults apply. Save one above to change how records are combined.</p>
        )}
        {!!ruleSets.data?.length && (
          <table className="data">
            <thead>
              <tr>
                <th>Name</th>
                <th>For</th>
                <th>Version</th>
                <th>Status</th>
                <th>What it does</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {ruleSets.data.map((rs: RuleSet) => (
                <tr key={rs.id}>
                  <td>{rs.name}</td>
                  <td>{TYPE_LABEL[rs.entity_type] ?? rs.entity_type}</td>
                  <td>v{rs.version}</td>
                  <td>
                    <Chip tone={rs.state === "published" ? "good" : "neutral"}>
                      {rs.state === "draft" ? "Draft" : rs.state === "published" ? "In use" : rs.state === "retired" ? "Replaced" : rs.state}
                    </Chip>
                  </td>
                  <td className="wrap">{describe(rs.document as Doc)}</td>
                  <td className="actions">
                    {(rs.state === "draft" || rs.state === "simulated") && (
                      <button type="button" className="btn small" disabled={!steward} title={denied} onClick={() => publish.mutate(rs.id)}>
                        Publish
                      </button>
                    )}
                    {rs.state === "retired" && (
                      <button type="button" className="btn small" disabled={!steward} title={denied} onClick={() => rollback.mutate(rs.id)}>
                        <Icon name="undo" size={14} /> Restore
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="page-section">
        <h2>Recent runs</h2>
        {jobs.isPending && <Skeleton rows={3} />}
        {jobs.isError && <ErrorNote error={jobs.error} />}
        {!!jobs.data?.length && (
          <table className="data">
            <thead>
              <tr>
                <th>When</th>
                <th>Status</th>
                <th>Started by</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {jobs.data.map((j) => (
                <tr key={j.id}>
                  <td title={new Date(j.created_at).toLocaleString()}>{relativeTime(j.created_at)}</td>
                  <td>
                    <Chip
                      tone={j.status === "succeeded" ? "good" : j.status === "failed" || effectiveStatus(j) === "stalled" ? "bad" : "accent"}
                      title={effectiveStatus(j) === "stalled" ? "This run never finished and is no longer waiting" : undefined}
                    >
                      {effectiveStatus(j)}
                    </Chip>
                  </td>
                  <td>{triggerLabel(j)}</td>
                  <td className="wrap">{runSummary(j)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ the remote control */

function Controls({ entityType, active, steward, onSaved }: { entityType: ErType; active: { name: string; version: string | null; document: RuleDoc }; steward: boolean; onSaved: () => void }) {
  const [doc, setDoc] = useState<RuleDoc>(active.document);
  const [name, setName] = useState(active.version ? active.name : `${entityType.toLowerCase()}-rules`);
  const dirty = useMemo(() => JSON.stringify(doc) !== JSON.stringify(active.document), [doc, active.document]);
  const s = doc.scoring;

  const setScoring = (patch: Partial<RuleDoc["scoring"]>) => setDoc({ ...doc, scoring: { ...s, ...patch } });
  const setAttr = (attr: string, patch: Partial<AttributeScoring>) =>
    setScoring({ attributes: { ...s.attributes, [attr]: { ...s.attributes[attr], ...patch } } });
  const body = { scoring: doc.scoring, constraints: doc.constraints };

  const preview = useMutation({ mutationFn: () => api.simulate(entityType, body) });
  const save = useMutation({
    mutationFn: async (publishNow: boolean) => {
      const rs = await api.createRuleSet({ name, entity_type: entityType, document: body });
      if (publishNow) await api.publishRuleSet(rs.id);
    },
    onSuccess: () => {
      preview.reset();
      onSaved();
    },
  });
  const valid = /^[a-z0-9][a-z0-9_-]{1,127}$/.test(name);
  const denied = steward ? undefined : "Requires the steward role";
  useEffect(() => preview.reset(), [doc]); // a preview describes the settings it was run with
  // eslint-disable-next-line react-hooks/exhaustive-deps

  return (
    <section className="page-section remote">
      <div className="remote-head">
        <div>
          <h2>Matching controls</h2>
          <p className="muted">
            Live now: <strong>{active.name}</strong>
            {active.version && ` ${active.version}`}. Change a lever, preview the effect on today's data, then save.
          </p>
        </div>
        {dirty && (
          <button type="button" className="btn small" onClick={() => setDoc(active.document)}>
            <Icon name="undo" size={14} /> Reset to live
          </button>
        )}
      </div>

      <div className="card">
        <h3>What a score decides</h3>
        <ScoreScale review={s.review} merge={s.auto_merge} />
        <div className="thresholds">
          <label className="field">
            <span>Send to review from {s.review}</span>
            <input
              type="range" min={0} max={100} value={s.review} disabled={!steward}
              onChange={(e) => {
                const review = Number(e.target.value);
                setScoring({ review, auto_merge: Math.max(review, s.auto_merge) });
              }}
            />
            <small>A person confirms or rejects the pair; until then it is drawn as a probable alias.</small>
          </label>
          <label className="field">
            <span>Merge automatically from {s.auto_merge}</span>
            <input
              type="range" min={0} max={100} value={s.auto_merge} disabled={!steward || !s.merge_by_score}
              onChange={(e) => {
                const auto_merge = Number(e.target.value);
                setScoring({ auto_merge, review: Math.min(auto_merge, s.review) });
              }}
            />
            <small>{s.merge_by_score ? "The records become one." : "Only with the switch below; otherwise a person decides."}</small>
          </label>
        </div>
        <label className="check">
          <input type="checkbox" checked={s.merge_by_score} disabled={!steward} onChange={(e) => setScoring({ merge_by_score: e.target.checked })} />
          <span>
            <strong>A high score can merge records on its own</strong>
            <small>
              Off: a score never merges; only a detail set to merge on its own, or a person's decision, does.
              Off is the safe setting for people, since a shared phone and address do not make two people one.
            </small>
          </span>
        </label>
      </div>

      <div className="card">
        <h3>How each detail counts</h3>
        <div className="levers-wrap">
          <table className="data levers">
            <thead>
              <tr>
                <th>Detail</th>
                <th>Indicator</th>
                <th>Compare</th>
                <th>If both differ</th>
                <th title="An exact match on this alone merges the records">Merges alone</th>
                <th title="Ignore a value held by more records than this (a switchboard, a registered agent)">Ignore if shared by more than</th>
                <th className="num">Points</th>
              </tr>
            </thead>
            <tbody>
              {Object.keys(s.attributes).map((key) => {
                const a = s.attributes[key];
                const meta = ATTRIBUTES[key] ?? { hint: "", compares: ["exact"] as Compare[] };
                const compares = key === "name" && entityType !== "Person" ? meta.compares.filter((c) => c !== "name_parts") : meta.compares;
                const points = a.strength === "off" ? 0 : s.weights[a.strength];
                return (
                  <tr key={key} className={a.strength === "off" && !a.merge_alone ? "lever-off" : ""}>
                    <td>
                      <strong>{attrLabel(key)}</strong>
                      <div className="muted small lever-hint">{meta.hint}</div>
                    </td>
                    <td>
                      <Segmented
                        label={`${attrLabel(key)} indicator`}
                        value={a.strength}
                        onChange={(v) => steward && setAttr(key, { strength: v })}
                        options={STRENGTHS}
                      />
                    </td>
                    <td>
                      {compares.length > 1 ? (
                        <>
                          <select value={a.compare} disabled={!steward} onChange={(e) => setAttr(key, { compare: e.target.value as Compare })} aria-label={`${attrLabel(key)} comparison`}>
                            {compares.map((c) => (
                              <option key={c} value={c}>{COMPARE_LABEL[c]}</option>
                            ))}
                          </select>
                          {(a.compare === "fuzzy" || a.compare === "name_parts") && (
                            <label className="slider-line">
                              <input
                                type="range" min={50} max={100} value={Math.round(a.min_similarity * 100)} disabled={!steward}
                                onChange={(e) => setAttr(key, { min_similarity: Number(e.target.value) / 100 })}
                                aria-label={`${attrLabel(key)} minimum similarity`}
                              />
                              <span className="small">
                                {a.compare === "name_parts" ? "first name" : "at least"} {Math.round(a.min_similarity * 100)}% alike
                              </span>
                            </label>
                          )}
                          {a.compare === "name_parts" && (
                            <div className="name-levers">
                              <label className="check small">
                                <input type="checkbox" checked={a.surname_exact} disabled={!steward} onChange={(e) => setAttr(key, { surname_exact: e.target.checked })} />
                                surname must be exact
                              </label>
                              <label className="check small">
                                <input type="checkbox" checked={a.nicknames} disabled={!steward} onChange={(e) => setAttr(key, { nicknames: e.target.checked })} />
                                nicknames and initials count
                              </label>
                            </div>
                          )}
                        </>
                      ) : (
                        <span className="muted">{COMPARE_LABEL[compares[0]]}</span>
                      )}
                    </td>
                    <td>
                      <select value={a.on_conflict} disabled={!steward} onChange={(e) => setAttr(key, { on_conflict: e.target.value as AttributeScoring["on_conflict"] })} aria-label={`${attrLabel(key)} when different`}>
                        <option value="ignore">Ignore it</option>
                        <option value="penalize">Take off points</option>
                        <option value="block">Never merge</option>
                      </select>
                      {a.on_conflict === "penalize" && (
                        <label className="slider-line">
                          <input
                            type="number" min={0} max={100} value={a.conflict_penalty} disabled={!steward}
                            onChange={(e) => setAttr(key, { conflict_penalty: Math.max(0, Math.min(100, Number(e.target.value) || 0)) })}
                            aria-label={`${attrLabel(key)} penalty`}
                          />
                          <span className="small">points</span>
                        </label>
                      )}
                    </td>
                    <td>
                      <input type="checkbox" checked={a.merge_alone} disabled={!steward} onChange={(e) => setAttr(key, { merge_alone: e.target.checked })} aria-label={`${attrLabel(key)} merges alone`} />
                    </td>
                    <td>
                      <input
                        type="number" min={2} placeholder="never" value={a.ignore_shared_over ?? ""} disabled={!steward}
                        onChange={(e) => setAttr(key, { ignore_shared_over: e.target.value ? Math.max(2, Number(e.target.value)) : null })}
                        aria-label={`${attrLabel(key)} ignore when shared by more than`}
                        className="narrow-input"
                      />
                    </td>
                    <td className="num">{points ? `+${points}` : "–"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {Object.entries(s.attributes).some(([k, a]) => a.merge_alone && ["bank_acct", "phone", "address", "device"].includes(k)) && (
          <div className="note warn">
            <Icon name="alert" size={16} />
            <span>
              Letting a bank account, phone, address or device merge records on its own merges the people and companies a ring is made of, and hides it.
            </span>
          </div>
        )}
      </div>

      <div className="card">
        <h3>Safeguards</h3>
        <label className="check">
          <input type="checkbox" checked={s.require_identity_match} disabled={!steward} onChange={(e) => setScoring({ require_identity_match: e.target.checked })} />
          <span>
            <strong>Require an identity match</strong>
            <small>
              Without one of the details ticked below matching, a pair sharing a bank account, email or phone is never merged or queued, however high it scores. This is what keeps rings visible.
            </small>
          </span>
        </label>
        <div className="identity-pick">
          <span className="muted small">Identity details:</span>
          {Object.keys(s.attributes).map((k) => (
            <label key={k} className="check small">
              <input
                type="checkbox" checked={s.identity.includes(k)} disabled={!steward || !s.require_identity_match}
                onChange={(e) => setScoring({ identity: e.target.checked ? [...s.identity, k] : s.identity.filter((x) => x !== k) })}
              />
              {attrLabel(k)}
            </label>
          ))}
        </div>
        <div className="form-row">
          <label className="field narrow">
            <span>Largest group allowed</span>
            <input type="number" min={2} max={500} value={doc.constraints.max_cluster_size} disabled={!steward}
              onChange={(e) => setDoc({ ...doc, constraints: { ...doc.constraints, max_cluster_size: Math.max(2, Math.min(500, Number(e.target.value) || 2)) } })} />
            <small>Stops a chain of weak matches from merging strangers into one record.</small>
          </label>
        </div>
        <details className="technical">
          <summary>Points per indicator</summary>
          <div className="weights">
            {(["strong", "medium", "low"] as const).map((k) => (
              <label key={k} className="field narrow">
                <span>{k[0].toUpperCase() + k.slice(1)}</span>
                <input type="number" min={0} max={100} value={s.weights[k]} disabled={!steward}
                  onChange={(e) => setScoring({ weights: { ...s.weights, [k]: Math.max(0, Math.min(100, Number(e.target.value) || 0)) } })} />
              </label>
            ))}
          </div>
          <small className="muted">A match earns these points (a fuzzy match earns them in proportion to how alike the values are). The score is the total, from 0 to 100.</small>
        </details>
      </div>

      <div className="card">
        <h3>Preview, then save</h3>
        <div className="form-actions">
          <button type="button" className="btn" disabled={!steward || preview.isPending} title={denied} onClick={() => preview.mutate()}>
            {preview.isPending ? "Working it out…" : "Preview impact"}
          </button>
          <label className="field inline">
            <span className="muted small">Save as</span>
            <input value={name} onChange={(e) => setName(e.target.value.toLowerCase())} aria-label="Rule set name" />
          </label>
          <button type="button" className="btn" disabled={!steward || !valid || !dirty || save.isPending} title={denied} onClick={() => save.mutate(false)}>
            Save as draft
          </button>
          <button type="button" className="btn primary" disabled={!steward || !valid || !dirty || save.isPending} title={denied} onClick={() => save.mutate(true)}>
            Save and publish
          </button>
        </div>
        <p className="muted small">A draft changes nothing until it is published. Publishing re-runs resolution.</p>
        {(preview.isError || save.isError) && <ErrorNote error={preview.error ?? save.error} />}
        {preview.data && (
          <div className="preview">
            <div className="stats">
              <div className="stat">
                <strong>{preview.data.entities}</strong>
                <span>entities (now {preview.data.current_entities})</span>
              </div>
              <div className="stat">
                <strong>{preview.data.changed_groups}</strong>
                <span>merged {preview.data.changed_groups === 1 ? "group differs" : "groups differ"} from today</span>
              </div>
              <div className="stat">
                <strong>{preview.data.review_pairs}</strong>
                <span>probable aliases for a person</span>
              </div>
              <div className="stat">
                <strong>{preview.data.blocked_by_conflict.toLocaleString()}</strong>
                <span>pairs blocked by a difference</span>
              </div>
            </div>
            {preview.data.merges.length > 0 && (
              <>
                <h4>Merged groups that would change</h4>
                <ul className="plain-list">
                  {preview.data.merges.map((m) => (
                    <li key={m.labels.join("|")}>
                      {m.labels.join(" · ")}
                      {m.records > m.labels.length && <span className="muted small"> and {m.records - m.labels.length} more</span>}
                    </li>
                  ))}
                </ul>
              </>
            )}
            {preview.data.reviews.length > 0 && (
              <>
                <h4>Strongest pairs left for review</h4>
                <ul className="plain-list">
                  {preview.data.reviews.map((r) => (
                    <li key={`${r.label_a}|${r.label_b}`}>
                      <Chip>{r.score}</Chip> {r.label_a} · {r.label_b}
                    </li>
                  ))}
                </ul>
              </>
            )}
            {preview.data.merges.length === 0 && preview.data.reviews.length === 0 && (
              <p className="muted">These settings change nothing on today's data.</p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

/** The 0-100 scale, cut into what happens at each score. */
function ScoreScale({ review, merge }: { review: number; merge: number }) {
  return (
    <div className="scale" role="img" aria-label={`Below ${review}: nothing. ${review} to ${merge}: review. ${merge} and above: merge.`}>
      <div className="scale-bar">
        <span className="z-none" style={{ width: `${review}%` }}>{review > 12 ? "Nothing" : ""}</span>
        <span className="z-review" style={{ width: `${Math.max(0, merge - review)}%` }}>{merge - review > 12 ? "Review" : ""}</span>
        <span className="z-merge" style={{ width: `${100 - merge}%` }}>{100 - merge > 8 ? "Merge" : ""}</span>
      </div>
      <div className="scale-ticks muted small">
        <span>0</span>
        <span>100</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ the review queue */

function ReviewQueue({ steward, onRun, running }: { steward: boolean; onRun: () => void; running: boolean }) {
  const qc = useQueryClient();
  const queue = useQuery({ queryKey: ["review-queue"], queryFn: api.reviewQueue });
  const [decided, setDecided] = useState(0);
  const decide = useMutation({
    mutationFn: (v: { pair: ReviewPair; kind: "confirm" | "reject" }) =>
      api.decide({ kind: v.kind, record_ids: [v.pair.record_a, v.pair.record_b], review_pair_id: v.pair.id }),
    onSuccess: () => {
      setDecided((n) => n + 1);
      qc.invalidateQueries({ queryKey: ["review-queue"] });
    },
  });
  return (
    <section className="page-section">
      <h2>Needs review {queue.data?.length ? <Chip tone="warn">{queue.data.length}</Chip> : null}</h2>
      {decided > 0 && (
        <div className="note">
          <Icon name="info" size={16} />
          <span>
            {plural(decided, "decision")} will apply on the next run.
          </span>
          <button type="button" className="btn small" disabled={!steward || running} onClick={() => { onRun(); setDecided(0); }}>
            Run now
          </button>
        </div>
      )}
      {queue.isPending && <Skeleton rows={3} />}
      {queue.isError && <ErrorNote error={queue.error} />}
      {decide.isError && <ErrorNote error={decide.error} />}
      {queue.data?.length === 0 && (
        <EmptyState icon="check" title="Nothing to review">
          Pairs that score between the review and merge scores wait here for a person to confirm or reject.
        </EmptyState>
      )}
      <div className="review-list">
        {queue.data?.map((p) => (
          <article key={p.id} className="review-card">
            <header>
              <Chip tone="warn" title="Match score, 0 to 100">{Math.round(p.score)}</Chip>
              <Chip>{TYPE_LABEL[p.contributions.entity_type] ?? p.contributions.entity_type}</Chip>
              <strong>{p.contributions.label_a}</strong>
              <span className="muted">and</span>
              <strong>{p.contributions.label_b}</strong>
            </header>
            <ul className="review-attrs">
              {p.contributions.attrs.map((a) => (
                <li key={a.attr} className={`ra-${a.outcome}`}>
                  <Icon name={a.outcome === "conflict" ? "close" : "check"} size={13} />
                  <span>{a.text}</span>
                  {a.outcome !== "match" && a.left !== a.right && (
                    <span className="muted small">
                      {" "}
                      “{a.left}” / “{a.right}”
                    </span>
                  )}
                </li>
              ))}
            </ul>
            <footer>
              <button type="button" className="btn small primary" disabled={!steward || decide.isPending} title={steward ? undefined : "Requires the steward role"} onClick={() => decide.mutate({ pair: p, kind: "confirm" })}>
                Same one
              </button>
              <button type="button" className="btn small" disabled={!steward || decide.isPending} title={steward ? undefined : "Requires the steward role"} onClick={() => decide.mutate({ pair: p, kind: "reject" })}>
                Different ones
              </button>
            </footer>
          </article>
        ))}
      </div>
    </section>
  );
}
