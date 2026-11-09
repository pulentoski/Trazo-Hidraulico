import { useEffect, useState } from "react";
import { fmt, parseNum } from "../lib/format";

/** Ícono «?» con ayuda contextual (visible al pasar el mouse o con el foco del teclado). */
export function Help({ text }: { text: string }) {
  return <span className="help" tabIndex={0} role="note" data-tip={text} aria-label={`Ayuda: ${text}`}>?</span>;
}

/** Texto de una etiqueta de campo, con ayuda opcional. */
export function FieldLabel({ label, help }: { label: string; help?: string }) {
  return <span>{label}{help && <Help text={help} />}</span>;
}

/** Campo numérico con coma decimal; confirma al salir o con Enter (una entrada de historial por edición). */
export function NumField({ label, value, unit, onCommit, digits = 3, allowNull = false, disabled, hint, invalid }: {
  label: string; value: number | null | undefined; unit?: string; onCommit: (v: number | null) => void;
  digits?: number; allowNull?: boolean; disabled?: boolean; hint?: string; invalid?: boolean;
}) {
  const show = (v: number | null | undefined) => (v === null || v === undefined ? "" : fmt(v, digits).replace(/\./g, "").replace(/(,\d*?)0+$/, "$1").replace(/,$/, ""));
  const [text, setText] = useState(show(value));
  const [focus, setFocus] = useState(false);
  useEffect(() => {
    if (!focus) setText(show(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, focus]);
  const commit = () => {
    const v = parseNum(text);
    if (v === null && !allowNull && text.trim() !== "") return setText(show(value));
    if (v !== (value ?? null)) onCommit(v);
  };
  return (
    <label className={`field num ${invalid ? "invalid" : ""}`}>
      <FieldLabel label={label} help={hint} />
      <div className="with-unit">
        <input inputMode="decimal" value={text} disabled={disabled} onFocus={() => setFocus(true)}
          onChange={(e) => setText(e.target.value)} onBlur={() => { setFocus(false); commit(); }}
          onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); if (e.key === "Escape") { setText(show(value)); (e.target as HTMLInputElement).blur(); } }} />
        {unit && <em>{unit}</em>}
      </div>
    </label>
  );
}

export function TextField({ label, value, onCommit, error, placeholder, hint }: {
  label: string; value: string | null | undefined; onCommit: (v: string) => void; error?: string | null; placeholder?: string; hint?: string;
}) {
  const [text, setText] = useState(value ?? "");
  useEffect(() => setText(value ?? ""), [value]);
  return (
    <label className={`field ${error ? "invalid" : ""}`}>
      <FieldLabel label={label} help={hint} />
      <input value={text} placeholder={placeholder} onChange={(e) => setText(e.target.value)}
        onBlur={() => text !== (value ?? "") && onCommit(text)}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
      {error && <small className="err">{error}</small>}
    </label>
  );
}

export function Readout({ label, value, unit, tone, hint }: { label: string; value: string; unit?: string; tone?: string; hint?: string }) {
  return <div className={`readout ${tone ?? ""}`}><FieldLabel label={label} help={hint} /><b>{value}</b>{unit && <em>{unit}</em>}</div>;
}
