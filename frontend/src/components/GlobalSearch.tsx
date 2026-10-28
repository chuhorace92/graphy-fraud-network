import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import type { SearchHit } from "../api/types";
import { VISUALS, badgeUri, entityKey, type VisualKey } from "../graph/icons";
import { attrLabel } from "../lib/friendly";
import { Icon } from "../ui/Icon";
import { ErrorNote } from "../ui/kit";

const typeKey = (h: SearchHit): VisualKey => entityKey(h.entity_type);

export function openEntity(id: string, hops = 1) {
  return `/investigate?entity=${encodeURIComponent(id)}&hops=${hops}`;
}

/** Type-ahead search over names, addresses, phones, emails and full IDs. Press "/" to focus.
 *  By default a pick opens that entity; `onPick` takes over (the canvas uses it to add one). */
export function GlobalSearch({
  variant = "bar",
  onPick,
  shortcut = true,
  placeholder,
  autoFocus = false,
}: {
  variant?: "bar" | "hero";
  onPick?: (hit: SearchHit) => void;
  shortcut?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
}) {
  const navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const listId = useId();
  const [text, setText] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(text.trim()), 250);
    return () => clearTimeout(t);
  }, [text]);

  const hits = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => api.search(debounced),
    enabled: debounced.length >= 2,
  });
  const results = hits.data ?? [];

  useEffect(() => setActive(0), [debounced]);

  // "/" focuses the search from anywhere that is not a text field.
  useEffect(() => {
    if (!shortcut) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) && !t.isContentEditable) {
        e.preventDefault();
        input.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [shortcut]);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const pick = (hit: SearchHit) => {
    setOpen(false);
    setText("");
    setDebounced("");
    if (onPick) return onPick(hit);
    input.current?.blur();
    navigate(openEntity(hit.entity_id));
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, Math.max(results.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" && results[active]) {
      e.preventDefault();
      pick(results[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
      input.current?.blur();
    }
  };

  const showPanel = open && text.trim().length > 0;
  return (
    <div className={`search search-${variant}`} ref={box}>
      <div className="search-field">
        <Icon name="search" size={variant === "hero" ? 22 : 17} />
        <input
          ref={input}
          role="combobox"
          aria-expanded={showPanel}
          aria-controls={listId}
          aria-activedescendant={results[active] ? `${listId}-${active}` : undefined}
          aria-label="Search people, companies, addresses, phones or IDs"
          autoFocus={autoFocus}
          placeholder={
            placeholder ?? (variant === "hero"
              ? "Search a name, address, phone number, email or full ID"
              : "Search people, companies, addresses, IDs…")
          }
          autoComplete="off"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
        {variant === "bar" && shortcut && !text && <kbd aria-hidden="true">/</kbd>}
        {text && (
          <button type="button" className="icon-btn" aria-label="Clear search" onClick={() => setText("")}>
            <Icon name="close" size={15} />
          </button>
        )}
      </div>

      {showPanel && (
        <div className="search-panel" id={listId} role="listbox">
          {text.trim().length < 2 && <p className="search-hint">Keep typing, at least 2 characters.</p>}
          {text.trim().length >= 2 && (hits.isFetching || debounced !== text.trim()) && results.length === 0 && (
            <p className="search-hint">Searching…</p>
          )}
          {hits.isError && <ErrorNote error={hits.error} />}
          {hits.isSuccess && debounced === text.trim() && results.length === 0 && (
            <p className="search-hint">
              No matches for “{debounced}”. Try a surname, a street, a phone number or a full ID.
            </p>
          )}
          {results.map((h, i) => (
            <div
              key={h.entity_id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={`hit ${i === active ? "on" : ""}`}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pick(h)}
            >
              <img src={badgeUri(typeKey(h))} alt="" width={26} height={26} />
              <span className="hit-main">
                <strong>{h.label}</strong>
                <span>
                  {h.entity_type}
                  {h.matched_on !== "name" && <> · matched {attrLabel(h.matched_on).toLowerCase()}</>}
                </span>
              </span>
              {h.matched_on in VISUALS && h.matched_on !== "name" && (
                <img
                  src={badgeUri(h.matched_on as VisualKey)}
                  alt=""
                  width={18}
                  height={18}
                  className="hit-via"
                />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
