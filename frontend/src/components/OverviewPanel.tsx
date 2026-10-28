import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { plural } from "../lib/friendly";
import { ErrorNote, Skeleton, Stat } from "../ui/kit";

/** The whole database at a glance: what is in it, how it clusters, and what resolution merged. */
export function OverviewPanel() {
  const q = useQuery({ queryKey: ["overview"], queryFn: api.overview });
  if (q.isPending) return <Skeleton rows={3} />;
  if (q.isError) return <ErrorNote error={q.error} />;
  const o = q.data;
  if (o.people + o.companies + o.claims + o.policies === 0) return null; // the lead grid explains
  return (
    <>
      <div className="stats overview">
        <Stat value={o.claims.toLocaleString()} label={o.claims === 1 ? "claim" : "claims"} />
        <Stat value={o.policies.toLocaleString()} label={o.policies === 1 ? "policy" : "policies"} />
        <Stat value={(o.people + o.companies).toLocaleString()} label="individuals and companies" />
        <Stat value={o.groups.toLocaleString()} label="connected groups" />
      </div>
      <p className="muted small">
        {plural(o.people, "individual")} and {plural(o.companies, "company", "companies")}.
        {o.largest_group > 0 && <> The largest group links {plural(o.largest_group, "entity", "entities")}.</>}{" "}
        Entity resolution built {plural(o.people, "person", "people")} from{" "}
        {plural(o.people_records, "source record")}:{" "}
        {o.merged_people > 0
          ? `${plural(o.merged_people, "person", "people")} combine ${o.merged_records.toLocaleString()} records that describe the same individual.`
          : "no records described the same individual."}
      </p>
    </>
  );
}
