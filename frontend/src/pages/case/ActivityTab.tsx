import type { CaseEvent } from "../../api/types";
import { formatDate, relativeTime } from "../../lib/friendly";
import { Icon, type IconName } from "../../ui/Icon";
import { EmptyState } from "../../ui/kit";
import type { TabProps } from "./shared";

const EVENT_ICON: Record<CaseEvent["kind"], IconName> = {
  note: "info",
  status: "check",
  assignee: "user",
  task: "tasks",
  document: "file",
  report: "report",
};

/** Everything that has happened on the case, newest first. Notes are written in the Notes tab. */
export function ActivityTab({ detail }: TabProps) {
  const { events } = detail;
  return (
    <div className="activity">
      {events.length === 0 ? (
        <EmptyState icon="history" title="No activity yet">
          Notes, tasks, documents and changes of status or owner are kept here.
        </EmptyState>
      ) : (
        <ol className="timeline">
          {[...events].reverse().map((e) => (
            <li key={e.id} className={`ev ev-${e.kind}`}>
              <span className="ev-icon">
                <Icon name={EVENT_ICON[e.kind]} size={14} />
              </span>
              <div>
                <p>{e.body}</p>
                <span className="muted small" title={formatDate(e.created_at)}>
                  {e.author} · {relativeTime(e.created_at)}
                </span>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
