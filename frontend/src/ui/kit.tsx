import type { ReactNode } from "react";

import { ApiError } from "../api/client";
import { Icon, type IconName } from "./Icon";

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string; hint?: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          title={o.hint}
          className={o.value === value ? "on" : ""}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.value}
          type="button"
          role="tab"
          aria-selected={t.value === value}
          className={t.value === value ? "on" : ""}
          onClick={() => onChange(t.value)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Chip({
  tone = "neutral",
  title,
  children,
}: {
  tone?: "neutral" | "accent" | "good" | "warn" | "bad";
  title?: string;
  children: ReactNode;
}) {
  return (
    <span className={`chip chip-${tone}`} title={title}>
      {children}
    </span>
  );
}

export function Stat({ value, label }: { value: ReactNode; label: string }) {
  return (
    <div className="stat">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({
  icon = "info",
  title,
  children,
  action,
}: {
  icon?: IconName;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Icon name={icon} size={22} />
      </span>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

/** A failed request, in words. Permission and "coming later" cases get their own wording. */
export function ErrorNote({ error }: { error: unknown }) {
  let text = "Something went wrong. Try again in a moment.";
  if (error instanceof ApiError) {
    if (error.status === 403) text = "Your role does not allow this.";
    else if (error.status === 404) text = "That item no longer exists.";
    else if (error.status === 501) text = error.message;
    else if (error.status >= 500) text = "The server hit a problem. Try again in a moment.";
    else text = error.message;
  } else if (error instanceof TypeError) {
    text = "Can't reach the server. Check your connection.";
  }
  return (
    <div className="error-note" role="alert">
      <Icon name="alert" size={16} />
      <span>{text}</span>
    </div>
  );
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="skeleton" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <span key={i} style={{ width: `${90 - ((i * 17) % 40)}%` }} />
      ))}
    </div>
  );
}
