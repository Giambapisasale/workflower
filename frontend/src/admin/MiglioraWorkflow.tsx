/** Casella "istruzione → miglioramento": l'admin scrive in italiano una regola
 * o una correzione, l'Improver la trasforma in una nuova versione della skill
 * (provata sul golden set) da approvare. Riusata in Revisione e Workflows. */

import { useState } from "react";
import { Link } from "react-router-dom";
import { ErroreApi } from "../shared/api";
import { admin, type Patch } from "./api";
import { Bottone } from "./ui";

export default function MiglioraWorkflow({
  workflow,
  runId,
  esempio = "Es. «individua sempre il fornitore dalla partita IVA, non dalla ragione sociale»",
  onFatto,
}: {
  workflow: string;
  runId?: string | null;
  esempio?: string;
  onFatto?: () => void;
}) {
  const [istruzione, setIstruzione] = useState("");
  const [inviando, setInviando] = useState(false);
  const [patch, setPatch] = useState<Patch | null>(null);
  const [errore, setErrore] = useState<string | null>(null);

  async function invia() {
    const testo = istruzione.trim();
    if (!testo) return;
    setInviando(true);
    setErrore(null);
    setPatch(null);
    try {
      const p = await admin.migliora(workflow, { run_id: runId ?? undefined, feedback: testo });
      setPatch(p);
      setIstruzione("");
      onFatto?.();
    } catch (e) {
      setErrore(
        e instanceof ErroreApi ? e.message : "Non è stato possibile proporre il miglioramento.",
      );
    } finally {
      setInviando(false);
    }
  }

  return (
    <div>
      <textarea
        value={istruzione}
        onChange={(e) => setIstruzione(e.target.value)}
        placeholder={esempio}
        rows={3}
        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
      />
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <Bottone variante="primario" onClick={invia} disabled={inviando || !istruzione.trim()}>
          {inviando ? "Propongo…" : "Proponi miglioramento"}
        </Bottone>
        <span className="text-xs text-slate-500">
          L'Improver riscrive la skill e la prova sui casi già validati; poi la approvi tu.
        </span>
      </div>
      {errore ? <div className="mt-2 text-sm text-red-600">{errore}</div> : null}
      {patch ? (
        <div className="mt-3 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800">
          Proposta <span className="font-mono">{patch.id}</span> creata · replay golden{" "}
          {patch.replay.ok}/{patch.replay.totale} ·{" "}
          <Link className="underline" to="/admin/workflows">
            rivedi e approva nei Workflows →
          </Link>
        </div>
      ) : null}
    </div>
  );
}
