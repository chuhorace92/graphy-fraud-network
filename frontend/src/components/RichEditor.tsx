import { useEffect, useRef } from "react";

type Command = { label: string; title: string; run: () => void };

/**
 * A small word-processor box: bold, italic, underline, headings, lists, quotes and links.
 * It edits HTML in place (the browser's own editing commands) and reports it on every change;
 * the server sanitizes whatever is saved. `value` is read once, so give it a `key` to start over.
 */
export function RichEditor({
  value,
  onChange,
  label = "Note text",
}: {
  value: string;
  onChange: (html: string) => void;
  label?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (box.current) box.current.innerHTML = value;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const exec = (command: string, arg?: string) => {
    box.current?.focus();
    document.execCommand(command, false, arg);
    onChange(box.current?.innerHTML ?? "");
  };
  const link = () => {
    const url = window.prompt("Link address (https://… or mailto:…)")?.trim();
    if (url && /^(https?:|mailto:)/i.test(url)) exec("createLink", url);
  };
  const tools: Command[] = [
    { label: "B", title: "Bold", run: () => exec("bold") },
    { label: "I", title: "Italic", run: () => exec("italic") },
    { label: "U", title: "Underline", run: () => exec("underline") },
    { label: "H", title: "Heading", run: () => exec("formatBlock", "h2") },
    { label: "¶", title: "Normal text", run: () => exec("formatBlock", "p") },
    { label: "• List", title: "Bulleted list", run: () => exec("insertUnorderedList") },
    { label: "1. List", title: "Numbered list", run: () => exec("insertOrderedList") },
    { label: "❝", title: "Quote", run: () => exec("formatBlock", "blockquote") },
    { label: "Link", title: "Link", run: link },
    { label: "Clear", title: "Remove formatting", run: () => exec("removeFormat") },
    { label: "↶", title: "Undo", run: () => exec("undo") },
    { label: "↷", title: "Redo", run: () => exec("redo") },
  ];
  return (
    <div className="rte">
      <div className="rte-bar" role="toolbar" aria-label="Formatting">
        {tools.map((t) => (
          <button
            key={t.title}
            type="button"
            className={`rte-btn rte-${t.title.toLowerCase().replace(/\W+/g, "-")}`}
            title={t.title}
            aria-label={t.title}
            onMouseDown={(e) => e.preventDefault()} // keep the selection in the text
            onClick={t.run}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div
        ref={box}
        className="rte-body note-body"
        contentEditable
        suppressContentEditableWarning
        role="textbox"
        aria-multiline="true"
        aria-label={label}
        onInput={() => onChange(box.current?.innerHTML ?? "")}
        onPaste={(e) => {
          // Pasted text comes in plain: Word and web pages carry far more than a note needs.
          e.preventDefault();
          document.execCommand("insertText", false, e.clipboardData.getData("text/plain"));
        }}
      />
    </div>
  );
}
