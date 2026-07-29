import type { EventoTrace } from "./api";
import { admin } from "./api";
import { useCarica } from "./formato";
import { Errore, Stato } from "./ui";

/** Il segno davanti alla riga: frecce e segni geometrici, non emoji — è la
 *  regola tipografica del design system Aitho. */
function riga(e: EventoTrace): { segno: string; testo: string } {
  const n = (k: string) => e[k] as number | undefined;
  const s = (k: string) => e[k] as string | undefined;
  switch (e.evento) {
    case "run_start":
      return { segno: "▶", testo: `avvio ${s("workflow")}@${s("version")} · ${s("input")}` };
    case "llm_call":
      return {
        segno: "·",
        testo: `${s("step")} · ${s("model")} · ${n("tokens_in")}+${n("tokens_out")} token · ${((n("cost_usd") ?? 0)).toFixed(4)}$ · ${n("latency_ms")}ms`,
      };
    case "tool_call":
      return { segno: e.ok ? "·" : "!", testo: `${s("step")} · ${s("name")} ${e.ok ? "ok" : "errore"}` };
    case "validation":
      return {
        segno: s("esito") === "ok" ? "✓" : "✗",
        testo: `verifica ${s("step")}: ${s("esito")}`,
      };
    case "run_end":
      return {
        segno: s("outcome") === "ok" ? "■" : "✗",
        testo: `fine: ${s("outcome")}${s("entity_id") ? ` → ${s("entity_id")}` : ""}${s("errore") ? ` (${s("errore")})` : ""}`,
      };
    case "operator_feedback":
      return { segno: "»", testo: `operatore (${s("tipo")}) · ${s("utente")}` };
    case "field_feedback":
      return { segno: "»", testo: `nota su ${s("campo")}: ${s("nota")} · ${s("utente")}` };
    case "escalation":
      return {
        segno: "↑",
        testo: `${s("step")} · rifatto da ${s("da")} a ${s("a")} · ${s("motivo")}`,
      };
    default: {
      // Un evento che questa funzione non conosce ancora: meglio mostrarne i campi
      // che il solo nome — un trace serve a capire, non a fare da indovinello.
      const campi = Object.entries(e)
        .filter(([k]) => !["evento", "ts", "run_id"].includes(k))
        .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
        .join(" · ");
      return { segno: "·", testo: campi ? `${e.evento} · ${campi}` : e.evento };
    }
  }
}

export default function TracePanel({ runId }: { runId: string }) {
  const { dati, errore, inCorso } = useCarica(() => admin.trace(runId), [runId]);
  if (inCorso) return <Stato>Carico il trace…</Stato>;
  if (errore) return <Errore>{errore}</Errore>;
  const eventi = dati ?? [];
  return (
    <div
      style={{
        background: "var(--dark)",
        borderRadius: "var(--radius)",
        padding: 12,
        fontFamily: "var(--font-mono), monospace",
        fontSize: 12,
        color: "#e6e6e6",
        overflow: "auto",
      }}
    >
      {eventi.map((e, i) => {
        const { segno, testo } = riga(e);
        return (
          <div key={i} style={{ display: "flex", gap: 10, padding: "2px 0" }}>
            <span style={{ width: 60, flexShrink: 0, color: "#8a8a8a" }}>
              {String(e.ts ?? "").slice(11, 19)}
            </span>
            <span style={{ width: 12, flexShrink: 0, color: "#8a8a8a" }}>{segno}</span>
            <span style={{ flex: 1 }}>{testo}</span>
          </div>
        );
      })}
    </div>
  );
}
