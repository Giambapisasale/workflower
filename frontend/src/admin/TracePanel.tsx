import type { EventoTrace } from "./api";
import { admin } from "./api";
import { useCarica } from "./formato";
import { Errore, Stato } from "./ui";

function riga(e: EventoTrace): { icona: string; testo: string } {
  const n = (k: string) => e[k] as number | undefined;
  const s = (k: string) => e[k] as string | undefined;
  switch (e.evento) {
    case "run_start":
      return { icona: "▶", testo: `avvio ${s("workflow")}@${s("version")} · ${s("input")}` };
    case "llm_call":
      return {
        icona: "🧠",
        testo: `${s("step")} · ${s("model")} · ${n("tokens_in")}+${n("tokens_out")} token · ${((n("cost_usd") ?? 0)).toFixed(4)}$ · ${n("latency_ms")}ms`,
      };
    case "tool_call":
      return { icona: e.ok ? "🔧" : "⚠️", testo: `${s("step")} · ${s("name")} ${e.ok ? "ok" : "errore"}` };
    case "validation":
      return { icona: s("esito") === "ok" ? "✅" : "❌", testo: `verifica ${s("step")}: ${s("esito")}` };
    case "run_end":
      return { icona: s("outcome") === "ok" ? "🏁" : "🛑", testo: `fine: ${s("outcome")}${s("entity_id") ? ` → ${s("entity_id")}` : ""}${s("errore") ? ` (${s("errore")})` : ""}` };
    case "operator_feedback":
      return { icona: "🗣️", testo: `operatore (${s("tipo")}) · ${s("utente")}` };
    case "field_feedback":
      return { icona: "📝", testo: `nota su ${s("campo")}: ${s("nota")} · ${s("utente")}` };
    default:
      return { icona: "·", testo: e.evento };
  }
}

export default function TracePanel({ runId }: { runId: string }) {
  const { dati, errore, inCorso } = useCarica(() => admin.trace(runId), [runId]);
  if (inCorso) return <Stato>Carico il trace…</Stato>;
  if (errore) return <Errore>{errore}</Errore>;
  const eventi = dati ?? [];
  return (
    <div className="rounded-lg bg-slate-900 p-3 font-mono text-xs text-slate-100">
      {eventi.map((e, i) => {
        const { icona, testo } = riga(e);
        return (
          <div key={i} className="flex gap-2 py-0.5">
            <span className="w-16 shrink-0 text-slate-500">{String(e.ts ?? "").slice(11, 19)}</span>
            <span className="w-5 shrink-0">{icona}</span>
            <span className="text-slate-200">{testo}</span>
          </div>
        );
      })}
    </div>
  );
}
