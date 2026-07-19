/** Skills & Tools (M12): tool nativi (Python), dataset di fine-tuning, e
 *  consolidamento delle query ricorrenti di “Interroga” in viste (v_*) o in
 *  tool parametrici (t_*) — le due forme del §3.6, entrambe dato, non codice. */

import { useState } from "react";
import { ErroreApi } from "../shared/api";
import { admin } from "./api";
import { dataBreve, useCarica } from "./formato";
import { Badge, Bottone, Card, Errore, Kpi, Stato } from "./ui";

type Modo = "vista" | "tool";

const CLASSE_INPUT = "rounded-lg border border-slate-300 px-2 py-1 text-sm";

export default function SkillsTools() {
  const { dati, errore, inCorso, ricarica } = useCarica(() =>
    Promise.all([admin.skillsTools(), admin.datasetStats()]),
  );
  const [apri, setApri] = useState<{ fp: string; modo: Modo } | null>(null);
  const [nome, setNome] = useState("");
  const [par, setPar] = useState<Record<string, string>>({}); // letterale → nome parametro
  const [salvando, setSalvando] = useState(false);
  const [erroreForm, setErroreForm] = useState<string | null>(null);
  const [conferma, setConferma] = useState<string | null>(null); // artefatto in attesa di conferma rimozione
  const [rimuovendo, setRimuovendo] = useState(false);
  const [erroreRim, setErroreRim] = useState<string | null>(null);

  if (inCorso) return <Stato>Carico tool e dataset…</Stato>;
  if (errore || !dati) return <Errore>{errore ?? "Nessun dato"}</Errore>;
  const [reg, stats] = dati;

  function apriForm(fp: string, modo: Modo) {
    setApri({ fp, modo });
    setNome("");
    setPar({});
    setErroreForm(null);
  }

  function chiudi() {
    setApri(null);
    setNome("");
    setPar({});
    setErroreForm(null);
  }

  async function creaVista(fp: string) {
    const scelto = nome.trim();
    if (!scelto) return;
    setSalvando(true);
    setErroreForm(null);
    try {
      await admin.consolida(fp, scelto);
      chiudi();
      ricarica();
    } catch (e) {
      setErroreForm(e instanceof ErroreApi ? e.message : "Consolidamento non riuscito");
    } finally {
      setSalvando(false);
    }
  }

  async function creaTool(fp: string) {
    const scelto = nome.trim();
    const parametri = Object.entries(par)
      .map(([valore, nm]) => ({ valore, nome: nm.trim() }))
      .filter((p) => p.nome);
    if (!scelto || parametri.length === 0) return;
    setSalvando(true);
    setErroreForm(null);
    try {
      await admin.consolidaTool(fp, scelto, parametri);
      chiudi();
      ricarica();
    } catch (e) {
      setErroreForm(e instanceof ErroreApi ? e.message : "Creazione del tool non riuscita");
    } finally {
      setSalvando(false);
    }
  }

  async function rimuovi(id: string, elimina: (id: string) => Promise<unknown>) {
    setRimuovendo(true);
    setErroreRim(null);
    try {
      await elimina(id);
      setConferma(null);
      ricarica();
    } catch (e) {
      setErroreRim(e instanceof ErroreApi ? e.message : "Rimozione non riuscita");
    } finally {
      setRimuovendo(false);
    }
  }

  const almenoUnParametro = Object.values(par).some((v) => v.trim());

  const azioniRimozione = (id: string, elimina: (id: string) => Promise<unknown>) =>
    conferma === id ? (
      <span className="flex items-center gap-2">
        <Bottone variante="pericolo" disabled={rimuovendo} onClick={() => rimuovi(id, elimina)}>
          {rimuovendo ? "Rimuovo…" : "Sì, rimuovi"}
        </Bottone>
        <Bottone onClick={() => setConferma(null)}>Annulla</Bottone>
      </span>
    ) : (
      <Bottone
        variante="pericolo"
        onClick={() => {
          setConferma(id);
          setErroreRim(null);
        }}
      >
        Rimuovi
      </Bottone>
    );

  return (
    <>
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
        <Kpi etichetta="Tool nativi" valore={reg.tools.length} nota="funzioni Python di sistema" />
        <Kpi etichetta="Tool call registrate" valore={stats.toolcalls_dataset} />
        <Kpi
          etichetta="Esempi fine-tuning"
          valore={stats.esempi_finetuning}
          nota="dai soli run validati"
        />
        <Kpi
          etichetta="Query ricorrenti"
          valore={reg.candidati.length}
          nota="candidate a vista/tool"
        />
        <Kpi etichetta="Viste consolidate" valore={reg.viste.length} nota="query → v_*" />
        <Kpi etichetta="Tool parametrici" valore={reg.macro.length} nota="query → t_*(…)" />
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

      <Card titolo="Tool nativi (Python)">
        <p className="mb-3 text-sm text-slate-600">
          Funzioni deterministiche di sistema che i workflow di caricamento invocano durante
          l'estrazione. Sono il set fisso incluso nell'app: non nascono dal consolidamento delle
          query (quelli sono viste e tool parametrici, qui sotto).
        </p>
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

      <Card titolo="Query ricorrenti — candidate al consolidamento">
        <p className="mb-3 text-sm text-slate-600">
          Ogni riga è una domanda che l'ufficio ha già posto a “Interroga”, con quante volte è
          tornata. Promuovila per non ripagare il modello e avere numeri stabili:{" "}
          <b>Crea vista</b> se è un totale o un elenco senza valori variabili; <b>Crea tool</b> se
          cambia solo un valore (es. il cantiere), che diventa un parametro.
        </p>
        {reg.candidati.length === 0 ? (
          <Stato>Nessuna query ricorrente: usa “Interroga” (modalità ufficio) per generarne.</Stato>
        ) : (
          <ul className="space-y-2 text-sm">
            {reg.candidati.map((c) => (
              <li key={c.fingerprint} className="border-b border-slate-50 pb-3">
                <div className="flex items-center gap-3">
                  <Badge tono={c.consolidato ? "verde" : c.conteggio > 1 ? "giallo" : "grigio"}>
                    ×{c.conteggio}
                  </Badge>
                  <code className="flex-1 truncate text-xs text-slate-500">{c.esempio}</code>
                  {c.consolidato ? (
                    <Badge tono="verde">✓ {c.consolidato}</Badge>
                  ) : apri?.fp === c.fingerprint ? (
                    <Bottone onClick={chiudi}>Annulla</Bottone>
                  ) : (
                    <div className="flex gap-2">
                      <Bottone onClick={() => apriForm(c.fingerprint, "vista")}>Crea vista</Bottone>
                      <Bottone onClick={() => apriForm(c.fingerprint, "tool")}>Crea tool</Bottone>
                    </div>
                  )}
                </div>

                {apri?.fp === c.fingerprint && apri.modo === "vista" && !c.consolidato ? (
                  <div className="mt-2 pl-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-slate-400">v_</span>
                      <input
                        autoFocus
                        className={`w-56 ${CLASSE_INPUT}`}
                        placeholder="spesa_per_cantiere"
                        value={nome}
                        onChange={(e) => setNome(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && creaVista(c.fingerprint)}
                      />
                      <Bottone
                        variante="primario"
                        disabled={salvando || !nome.trim()}
                        onClick={() => creaVista(c.fingerprint)}
                      >
                        {salvando ? "Creo…" : "Crea vista"}
                      </Bottone>
                    </div>
                    <p className="mt-1 text-xs text-slate-400">
                      Diventa una vista <code>v_&lt;nome&gt;</code> permanente: niente più modello,
                      numeri sempre uguali. Puoi poi interrogarla per nome.
                    </p>
                    {erroreForm ? (
                      <div className="mt-2">
                        <Errore>{erroreForm}</Errore>
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {apri?.fp === c.fingerprint && apri.modo === "tool" && !c.consolidato ? (
                  <div className="mt-2 pl-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-slate-400">t_</span>
                      <input
                        autoFocus
                        className={`w-56 ${CLASSE_INPUT}`}
                        placeholder="spesa_per_cantiere"
                        value={nome}
                        onChange={(e) => setNome(e.target.value)}
                      />
                    </div>
                    {c.letterali.length === 0 ? (
                      <p className="mt-2 text-xs text-slate-400">
                        Nessun valore da parametrizzare in questa query: conviene “Crea vista”.
                      </p>
                    ) : (
                      <>
                        <p className="mt-2 text-xs text-slate-500">
                          Scegli quali valori diventano <b>parametri</b> (lascia vuoto per tenerli
                          fissi):
                        </p>
                        <div className="mt-1 space-y-1">
                          {c.letterali.map((lit) => (
                            <div key={lit} className="flex items-center gap-2">
                              <code className="w-40 shrink-0 truncate text-xs text-slate-600">
                                {lit}
                              </code>
                              <span className="text-slate-300">→</span>
                              <input
                                className={`w-52 ${CLASSE_INPUT}`}
                                placeholder="nome parametro (es. cantiere)"
                                value={par[lit] ?? ""}
                                onChange={(e) =>
                                  setPar((p) => ({ ...p, [lit]: e.target.value }))
                                }
                              />
                            </div>
                          ))}
                        </div>
                      </>
                    )}
                    <div className="mt-2">
                      <Bottone
                        variante="primario"
                        disabled={salvando || !nome.trim() || !almenoUnParametro}
                        onClick={() => creaTool(c.fingerprint)}
                      >
                        {salvando ? "Creo…" : "Crea tool"}
                      </Bottone>
                    </div>
                    <p className="mt-1 text-xs text-slate-400">
                      Diventa <code>t_&lt;nome&gt;(parametri)</code>: una funzione stabile richiamabile
                      con valori diversi. “Interroga” la userà al posto di riscrivere la query.
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
            Nessuna vista consolidata: premi “Crea vista” su una query ricorrente qui sopra.
          </Stato>
        ) : (
          <>
            <ul className="space-y-2 text-sm">
              {reg.viste.map((v) => (
                <li key={v.vista} className="flex items-center gap-3 border-b border-slate-50 pb-2">
                  <Badge tono="verde">{v.vista}</Badge>
                  <code className="flex-1 truncate text-xs text-slate-500">{v.corpo}</code>
                  <span className="whitespace-nowrap text-xs text-slate-400">
                    {dataBreve(v.creato)} · {v.creato_da}
                  </span>
                  {azioniRimozione(v.vista, admin.eliminaVista)}
                </li>
              ))}
            </ul>
            {erroreRim && conferma?.startsWith("v_") ? (
              <div className="mt-3">
                <Errore>{erroreRim}</Errore>
              </div>
            ) : null}
          </>
        )}
      </Card>

      <Card titolo="Tool parametrici (macro)">
        {reg.macro.length === 0 ? (
          <Stato>
            Nessun tool: premi “Crea tool” su una query ricorrente con un valore variabile.
          </Stato>
        ) : (
          <>
            <p className="mb-3 text-sm text-slate-600">
              Per <b>modificarne</b> uno, rimuovilo: la query torna tra le “ricorrenti” qui sopra e
              puoi ricrearlo con nome o parametri diversi. Ogni rimozione è un commit git,
              reversibile.
            </p>
            <ul className="space-y-2 text-sm">
              {reg.macro.map((m) => (
                <li key={m.macro} className="flex items-center gap-3 border-b border-slate-50 pb-2">
                  <Badge tono="blu">
                    {m.macro}({m.parametri.join(", ")})
                  </Badge>
                  <code className="flex-1 truncate text-xs text-slate-500">{m.corpo}</code>
                  <span className="whitespace-nowrap text-xs text-slate-400">
                    {dataBreve(m.creato)} · {m.creato_da}
                  </span>
                  {azioniRimozione(m.macro, admin.eliminaTool)}
                </li>
              ))}
            </ul>
            {erroreRim && conferma?.startsWith("t_") ? (
              <div className="mt-3">
                <Errore>{erroreRim}</Errore>
              </div>
            ) : null}
          </>
        )}
      </Card>
    </>
  );
}
