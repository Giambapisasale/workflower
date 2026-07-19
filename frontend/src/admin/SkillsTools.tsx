/** Skills & Tools (M12): registry dei tool, dataset di fine-tuning, candidati. */

import { useState } from "react";
import { ErroreApi } from "../shared/api";
import { admin } from "./api";
import { dataBreve, useCarica } from "./formato";
import { Badge, Bottone, Card, Errore, Kpi, Stato } from "./ui";

export default function SkillsTools() {
  const { dati, errore, inCorso, ricarica } = useCarica(() =>
    Promise.all([admin.skillsTools(), admin.datasetStats()]),
  );
  const [apri, setApri] = useState<string | null>(null); // fingerprint con il form aperto
  const [nome, setNome] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erroreForm, setErroreForm] = useState<string | null>(null);

  if (inCorso) return <Stato>Carico tool e dataset…</Stato>;
  if (errore || !dati) return <Errore>{errore ?? "Nessun dato"}</Errore>;
  const [reg, stats] = dati;

  function apriForm(fingerprint: string) {
    setApri(fingerprint);
    setNome("");
    setErroreForm(null);
  }

  async function consolida(fingerprint: string) {
    const scelto = nome.trim();
    if (!scelto) return;
    setSalvando(true);
    setErroreForm(null);
    try {
      await admin.consolida(fingerprint, scelto);
      setApri(null);
      setNome("");
      ricarica();
    } catch (e) {
      setErroreForm(e instanceof ErroreApi ? e.message : "Consolidamento non riuscito");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-5">
        <Kpi etichetta="Tool nativi" valore={reg.tools.length} />
        <Kpi etichetta="Tool call registrate" valore={stats.toolcalls_dataset} />
        <Kpi
          etichetta="Esempi fine-tuning"
          valore={stats.esempi_finetuning}
          nota="dai soli run validati"
        />
        <Kpi etichetta="Candidati a tool" valore={reg.candidati.length} />
        <Kpi etichetta="Viste consolidate" valore={reg.viste.length} nota="query promosse a v_*" />
      </div>

      <Card
        titolo="Dataset per il fine-tuning (FunctionGemma)"
        azioni={
          <Bottone onClick={() => admin.scaricaFinetuning()} disabled={stats.esempi_finetuning === 0}>
            ⬇ Scarica finetuning.jsonl
          </Bottone>
        }
      >
        <p className="text-sm text-slate-600">
          Solo le tool call dei documenti <b>validati dall'ufficio</b> diventano esempi di
          addestramento: {stats.esempi_finetuning} pronti. Serviranno a distillare i workflow
          consolidati su un modello locale (tier T3), portando il costo per documento verso zero.
        </p>
      </Card>

      <Card titolo="Registry dei tool">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
              <th className="pb-2">Tool</th>
              <th className="pb-2">Cosa fa</th>
              <th className="pb-2 text-right">Usi</th>
              <th className="pb-2">Ciclo di vita</th>
            </tr>
          </thead>
          <tbody>
            {reg.tools.map((t) => (
              <tr key={t.name} className="border-b border-slate-50">
                <td className="py-2 font-mono text-xs text-slate-700">{t.name}</td>
                <td className="py-2 text-slate-600">{t.descrizione}</td>
                <td className="py-2 text-right tabular-nums">{t.usi}</td>
                <td className="py-2">
                  <Badge tono="verde">{t.ciclo}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card titolo="Candidati al consolidamento">
        {reg.candidati.length === 0 ? (
          <Stato>Nessuna query ricorrente da consolidare: usa “Interroga” per generarne.</Stato>
        ) : (
          <ul className="space-y-2 text-sm">
            {reg.candidati.map((c) => (
              <li key={c.fingerprint} className="border-b border-slate-50 pb-2">
                <div className="flex items-center gap-3">
                  <Badge tono={c.consolidato ? "verde" : c.conteggio > 1 ? "giallo" : "grigio"}>
                    ×{c.conteggio}
                  </Badge>
                  <code className="flex-1 truncate text-xs text-slate-500">{c.esempio}</code>
                  {c.consolidato ? (
                    <Badge tono="verde">✓ {c.consolidato}</Badge>
                  ) : apri === c.fingerprint ? (
                    <Bottone onClick={() => setApri(null)}>Annulla</Bottone>
                  ) : (
                    <Bottone onClick={() => apriForm(c.fingerprint)}>Consolida</Bottone>
                  )}
                </div>
                {apri === c.fingerprint && !c.consolidato ? (
                  <div className="mt-2 pl-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-slate-400">v_</span>
                      <input
                        autoFocus
                        className="w-56 rounded-lg border border-slate-300 px-2 py-1 text-sm"
                        placeholder="spesa_per_cantiere"
                        value={nome}
                        onChange={(e) => setNome(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && consolida(c.fingerprint)}
                      />
                      <Bottone
                        variante="primario"
                        disabled={salvando || !nome.trim()}
                        onClick={() => consolida(c.fingerprint)}
                      >
                        {salvando ? "Creo…" : "Crea vista"}
                      </Bottone>
                    </div>
                    <p className="mt-1 text-xs text-slate-400">
                      Diventa una vista <code>v_&lt;nome&gt;</code> permanente: niente più modello, numeri
                      sempre uguali. Puoi poi interrogarla per nome.
                    </p>
                    {erroreForm ? (
                      <div className="mt-2">
                        <Errore>{erroreForm}</Errore>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card titolo="Viste consolidate">
        {reg.viste.length === 0 ? (
          <Stato>
            Nessuna vista consolidata: premi “Consolida” su un candidato ricorrente qui sopra.
          </Stato>
        ) : (
          <ul className="space-y-2 text-sm">
            {reg.viste.map((v) => (
              <li key={v.vista} className="flex items-center gap-3 border-b border-slate-50 pb-2">
                <Badge tono="verde">{v.vista}</Badge>
                <code className="flex-1 truncate text-xs text-slate-500">{v.corpo}</code>
                <span className="whitespace-nowrap text-xs text-slate-400">
                  {dataBreve(v.creato)} · {v.creato_da}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
