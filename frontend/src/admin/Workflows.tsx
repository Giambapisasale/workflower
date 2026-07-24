import { useState } from "react";
import { admin, type EsitoApprovazione, type Patch } from "./api";
import DiffView from "./DiffView";
import { dataBreve, euro, useCarica } from "./formato";
import MiglioraWorkflow from "./MiglioraWorkflow";
import { Badge, Bottone, Card, Errore, Stato } from "./ui";

function PatchCard({ patch, onFatto }: { patch: Patch; onFatto: () => void }) {
  const [azione, setAzione] = useState<string | null>(null);
  const [esito, setEsito] = useState<EsitoApprovazione | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const replayOk = patch.replay.ok === patch.replay.totale;

  async function decidi(tipo: "approva" | "rifiuta") {
    setAzione(tipo);
    setErrore(null);
    try {
      if (tipo === "approva") setEsito(await admin.approva(patch.id));
      else {
        await admin.rifiuta(patch.id);
        onFatto();
      }
    } catch {
      setErrore("Operazione non riuscita.");
    } finally {
      setAzione(null);
    }
  }

  if (esito) {
    const rer = esito.rerun;
    return (
      <div className="rounded-lg border border-green-200 bg-green-50 p-4">
        <div className="font-medium text-green-800">
          ✅ {patch.id} approvata → {patch.workflow} v{esito.versione}
        </div>
        {rer ? (
          <div className="mt-1 text-sm text-green-700">
            Documento d'origine rielaborato ({rer.entity_id}
            {rer.ritenuta != null ? `, ritenuta ${euro(rer.ritenuta)}` : ""}).
          </div>
        ) : null}
        <div className="mt-3">
          <Bottone onClick={onFatto}>Aggiorna</Bottone>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="font-mono text-sm font-semibold">{patch.id}</span>
        <Badge tono="blu">{patch.workflow}</Badge>
        <span className="text-sm text-slate-500">v{patch.da_versione} → v{patch.a_versione}</span>
        <span className="ml-auto text-xs text-slate-400">{dataBreve(patch.creato)}</span>
      </div>
      <p className="text-sm text-slate-700"><strong>Analisi:</strong> {patch.analisi}</p>
      <p className="text-sm text-slate-700"><strong>Motivo:</strong> {patch.motivazione}</p>

      <div className="my-3 flex items-center gap-2">
        <Badge tono={replayOk ? "verde" : "rosso"}>
          Replay golden {patch.replay.ok}/{patch.replay.totale}
        </Badge>
        {!replayOk ? (
          <span className="text-xs text-red-600">
            {patch.replay.casi
              .filter((c) => !c.uguale)
              .map((c) => `${c.golden_id} (${c.differenze.join(", ")})`)
              .join("; ")}
          </span>
        ) : (
          <span className="text-xs text-slate-500">nessuna regressione sui casi validati</span>
        )}
      </div>

      <DiffView diff={patch.diff_skill} />

      {errore ? <div className="mt-2 text-sm text-red-600">{errore}</div> : null}
      <div className="mt-3 flex gap-2">
        <Bottone variante="primario" onClick={() => decidi("approva")} disabled={azione !== null}>
          {azione === "approva" ? "Applico…" : "Approva e applica"}
        </Bottone>
        <Bottone variante="pericolo" onClick={() => decidi("rifiuta")} disabled={azione !== null}>
          Rifiuta
        </Bottone>
        {!replayOk ? (
          <span className="self-center text-xs text-amber-700">
            ⚠ il replay segnala regressioni: approva solo se sai cosa fai
          </span>
        ) : null}
      </div>
    </div>
  );
}

export default function Workflows() {
  const [chiave, setChiave] = useState(0);
  const [apri, setApri] = useState<string | null>(null);
  const reload = () => setChiave((k) => k + 1);
  const wf = useCarica(() => admin.workflows(), [chiave]);
  const pt = useCarica(() => admin.patches("proposta"), [chiave]);

  const patches = pt.dati ?? [];
  const workflows = wf.dati ?? [];

  return (
    <>
      {patches.length > 0 ? (
        <Card titolo={`Patch in attesa (${patches.length})`}>
          <div className="space-y-4">
            {patches.map((p) => (
              <PatchCard key={p.id} patch={p} onFatto={reload} />
            ))}
          </div>
        </Card>
      ) : null}

      <Card titolo="Workflow">
        {wf.inCorso ? (
          <Stato>Carico i workflow…</Stato>
        ) : wf.errore ? (
          <Errore>{wf.errore}</Errore>
        ) : (
          <div className="space-y-4">
            {workflows.map((w) => (
              <div key={w.name} className="rounded-lg border border-slate-200 p-4">
                <div className="flex items-center gap-3">
                  <span className="font-mono font-semibold text-slate-800">{w.name}</span>
                  <Badge tono="blu">v{w.version}</Badge>
                  {w.tier ? <Badge tono="grigio">{w.tier}</Badge> : null}
                </div>
                {w.steps.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {w.steps.map((s) => (
                      <span key={s} className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{s}</span>
                    ))}
                  </div>
                ) : null}
                <div className="mt-3 flex flex-wrap gap-6 text-sm text-slate-600">
                  <span><span className="font-semibold text-slate-800">{w.stats.totale}</span> run</span>
                  <span className="text-green-700">{w.stats.ok} ok</span>
                  <span className="text-red-600">{w.stats.errore} errore</span>
                  <span><span className="font-semibold text-slate-800">{w.golden}</span> casi golden</span>
                  {w.confidence_threshold !== null ? (
                    <span className="text-slate-400">soglia confidenza {w.confidence_threshold}</span>
                  ) : null}
                </div>
                <div className="mt-3 border-t border-slate-100 pt-3">
                  <button
                    type="button"
                    onClick={() => setApri(apri === w.name ? null : w.name)}
                    className="text-sm font-medium text-sky-700 hover:underline"
                  >
                    {apri === w.name ? "▾ chiudi" : "✎ Migliora con un'istruzione"}
                  </button>
                  {apri === w.name ? (
                    <div className="mt-3">
                      <MiglioraWorkflow workflow={w.name} onFatto={reload} />
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </>
  );
}
