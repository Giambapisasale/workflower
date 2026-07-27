/** Toolsmith (F3): un calcolo che l'ufficio corregge sempre allo stesso modo
 *  diventa una funzione Python deterministica.
 *
 *  L'esempio guida è la ritenuta d'acconto: finché la calcola il prompt costa
 *  token a ogni fattura e a volte sbaglia. Il patto è: i **test si generano dalle
 *  coppie già validate** dall'ufficio, il codice gira **solo in sandbox**, e nulla
 *  si attiva senza un sì umano. Il backend è M16–M17; questo è il pannello che
 *  mancava per usarlo senza curl. */

import { useState } from "react";
import { Link } from "react-router-dom";
import { ErroreApi } from "../shared/api";
import { admin, type CandidatoToolsmith, type CasoTest, type PropostaTool } from "./api";
import { dataBreve, useCarica } from "./formato";
import { Badge, Bottone, Card, Errore, Stato } from "./ui";

const CLASSE_INPUT = "rounded-lg border border-slate-300 px-2 py-1 text-sm";

/** "ritenuta_acconto" → "ritenuta_acconto" già va bene come nome tool. */
function nomeSuggerito(campo: string): string {
  return `calcola_${campo}`.slice(0, 40).replace(/[^a-z0-9_]/g, "_");
}

function valoriDiEsempio(valori: unknown[]): string {
  return valori
    .slice(0, 3)
    .map((v) => (typeof v === "object" ? JSON.stringify(v) : String(v)))
    .join(", ");
}

function tonoStato(stato: string): string {
  return stato === "approvata" ? "verde" : stato === "rifiutata" ? "grigio" : "giallo";
}

// ------------------------------------------------------------------ candidati

function FormProposta({
  candidato,
  campiDisponibili,
  onFatto,
  onAnnulla,
}: {
  candidato: CandidatoToolsmith;
  campiDisponibili: string[];
  onFatto: () => void;
  onAnnulla: () => void;
}) {
  const [nome, setNome] = useState(nomeSuggerito(candidato.campo));
  const [ingressi, setIngressi] = useState<string[]>([]);
  const [inCorso, setInCorso] = useState(false);
  const [errore, setErrore] = useState<string | null>(null);

  function commuta(campo: string) {
    setIngressi((prec) =>
      prec.includes(campo) ? prec.filter((c) => c !== campo) : [...prec, campo],
    );
  }

  async function proponi() {
    setInCorso(true);
    setErrore(null);
    try {
      await admin.toolsmithProponi({
        nome: nome.trim(),
        tipo: candidato.tipo ?? "",
        campi_input: ingressi,
        campo_output: candidato.campo,
        workflow: candidato.workflow,
      });
      onFatto();
    } catch (e) {
      setErrore(e instanceof ErroreApi ? e.message : "Non è stato possibile generare la proposta.");
    } finally {
      setInCorso(false);
    }
  }

  return (
    <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50/60 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-500">Nome del tool</span>
        <input
          autoFocus
          className={`w-56 ${CLASSE_INPUT}`}
          value={nome}
          onChange={(e) => setNome(e.target.value)}
        />
        <span className="text-xs text-slate-400">minuscole, numeri e underscore</span>
      </div>

      <p className="mt-3 text-xs text-slate-500">
        Da quali campi si <b>ricava</b> <code>{candidato.campo}</code>? Il tool riceverà solo
        questi.
      </p>
      <div className="mt-1 flex flex-wrap gap-2">
        {campiDisponibili
          .filter((c) => c !== candidato.campo)
          .map((campo) => (
            <button
              key={campo}
              type="button"
              onClick={() => commuta(campo)}
              className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                ingressi.includes(campo)
                  ? "bg-sky-100 text-sky-800"
                  : "border border-slate-300 bg-white text-slate-600"
              }`}
            >
              {campo}
            </button>
          ))}
      </div>

      <div className="mt-3 flex gap-2">
        <Bottone
          variante="primario"
          onClick={proponi}
          disabled={inCorso || !nome.trim() || ingressi.length === 0}
        >
          {inCorso ? "Genero…" : "Genera la proposta"}
        </Bottone>
        <Bottone onClick={onAnnulla} disabled={inCorso}>Annulla</Bottone>
      </div>
      <p className="mt-1 text-xs text-slate-400">
        Genera codice e schema col modello, poi esegue in sandbox i test ricavati dagli esempi
        validati. Nulla viene attivato: resta una proposta da approvare.
      </p>

      {errore ? (
        <div className="mt-2">
          <Errore>{errore}</Errore>
        </div>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------- proposte

function Casi({ casi }: { casi: CasoTest[] }) {
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-left uppercase text-slate-400">
          <th className="pb-1 pr-3">Argomenti</th>
          <th className="pb-1 pr-3">Atteso</th>
          <th className="pb-1 pr-3">Ottenuto</th>
          <th className="pb-1"></th>
        </tr>
      </thead>
      <tbody>
        {casi.map((caso, i) => (
          <tr key={i} className="border-b border-slate-50 align-top">
            <td className="py-1 pr-3 font-mono text-slate-600">
              {JSON.stringify(caso.argomenti)}
            </td>
            <td className="py-1 pr-3 font-mono text-slate-600">{JSON.stringify(caso.atteso)}</td>
            <td className="py-1 pr-3 font-mono text-slate-600">
              {caso.errore ? (
                <span className="text-red-700">{caso.errore}</span>
              ) : (
                JSON.stringify(caso.ottenuto ?? null)
              )}
            </td>
            <td className="py-1">{caso.ok ? "✅" : "❌"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SchedaProposta({ proposta, onDeciso }: { proposta: PropostaTool; onDeciso: () => void }) {
  const [aperta, setAperta] = useState(false);
  const [azione, setAzione] = useState<string | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [esito, setEsito] = useState<string | null>(null);

  const test = proposta.esito_test ?? { totale: 0, ok: 0, casi: [] };
  const tuttiOk = test.totale > 0 && test.ok === test.totale;

  async function decidi(quale: "approva" | "rifiuta") {
    setAzione(quale);
    setErrore(null);
    try {
      if (quale === "rifiuta") {
        await admin.toolsmithRifiuta(proposta.id);
        setEsito("Proposta rifiutata: nessun tool registrato, nessuna skill toccata.");
      } else {
        const r = await admin.toolsmithApprova(proposta.id);
        setEsito(
          r.patch_skill
            ? `Tool ${r.pytool} registrato. È nata una patch di skill (${r.patch_skill.id}) ` +
              `con replay ${r.patch_skill.replay.ok}/${r.patch_skill.replay.totale}: ` +
              "approvala nei Workflows."
            : `Tool ${r.pytool} registrato. Nessuna skill da patchare per questo candidato.`,
        );
      }
      onDeciso();
    } catch (e) {
      setErrore(e instanceof ErroreApi ? e.message : "Operazione non riuscita.");
    } finally {
      setAzione(null);
    }
  }

  return (
    <li className="border-b border-slate-100 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <Badge tono={tonoStato(proposta.stato)}>{proposta.stato}</Badge>
        <code className="font-mono text-sm text-slate-800">{proposta.nome}</code>
        <span className="text-xs text-slate-500">
          {proposta.candidato.campi_input.join(", ")} → {proposta.candidato.campo_output}
        </span>
        <Badge tono={tuttiOk ? "verde" : "rosso"}>
          test {test.ok}/{test.totale}
        </Badge>
        <span className="text-xs text-slate-400">
          {proposta.esempi} esempi validati · {dataBreve(proposta.creato)}
        </span>
        <span className="ml-auto flex gap-2">
          <Bottone onClick={() => setAperta((v) => !v)}>
            {aperta ? "Nascondi" : "Ispeziona"}
          </Bottone>
          {proposta.stato === "proposta" ? (
            <>
              <Bottone
                variante="primario"
                onClick={() => decidi("approva")}
                disabled={azione !== null}
              >
                {azione === "approva" ? "Approvo…" : "Approva"}
              </Bottone>
              <Bottone
                variante="pericolo"
                onClick={() => decidi("rifiuta")}
                disabled={azione !== null}
              >
                Rifiuta
              </Bottone>
            </>
          ) : null}
        </span>
      </div>

      {!tuttiOk && proposta.stato === "proposta" ? (
        <p className="mt-2 text-xs text-amber-700">
          Il codice generato non passa tutti i test ricavati dai casi validati: approvarlo
          significherebbe consolidare un calcolo sbagliato.
        </p>
      ) : null}

      {esito ? (
        <div className="mt-2 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-800">
          {esito}{" "}
          <Link className="underline" to="/admin/workflows">vai ai Workflows</Link>
        </div>
      ) : null}

      {aperta ? (
        <div className="mt-3 space-y-3">
          <div>
            <div className="mb-1 text-xs font-medium uppercase text-slate-400">
              Codice (eseguito solo in sandbox)
            </div>
            <pre className="max-h-72 overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
              {proposta.codice}
            </pre>
          </div>
          <div>
            <div className="mb-1 text-xs font-medium uppercase text-slate-400">
              Test dai casi già validati
            </div>
            <Casi casi={test.casi ?? []} />
          </div>
          <details>
            <summary className="cursor-pointer text-xs text-slate-500">Schema del tool</summary>
            <pre className="mt-1 max-h-48 overflow-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
              {JSON.stringify(proposta.schema, null, 2)}
            </pre>
          </details>
        </div>
      ) : null}

      {errore ? (
        <div className="mt-2">
          <Errore>{errore}</Errore>
        </div>
      ) : null}
    </li>
  );
}

// ------------------------------------------------------------------ pannello

export default function Toolsmith() {
  const candidati = useCarica(() => admin.toolsmithCandidati());
  const proposte = useCarica(() => admin.toolsmithProposte());
  const meta = useCarica(() => admin.entitiesMeta());
  const [apri, setApri] = useState<string | null>(null);

  function campiDi(tipo: string | null): string[] {
    const voce = (meta.dati ?? []).find((t) => t.tipo === tipo);
    return Object.keys(voce?.schema.properties ?? {}).filter((c) => c !== "righe");
  }

  function ricaricaTutto() {
    candidati.ricarica();
    proposte.ricarica();
  }

  return (
    <>
      <Card titolo="Candidati Python — calcoli che l'ufficio corregge sempre">
        <p className="mb-3 text-sm text-slate-600">
          Ogni riga è un campo che la revisione ha corretto più volte: il segnale che
          l'estrazione lo sta <em>ragionando</em> quando invece lo si può <em>calcolare</em>. Serve
          un minimo di casi validati (3) perché ci sia materia per generare e per testare.
        </p>

        {candidati.errore ? <Errore>{candidati.errore}</Errore> : null}
        {candidati.inCorso ? (
          <Stato>Carico i candidati…</Stato>
        ) : (candidati.dati ?? []).length === 0 ? (
          <Stato>
            Nessun candidato: nasce dal delta fra bozza estratta e dato validato, quindi serve
            aver corretto e validato qualche documento.
          </Stato>
        ) : (
          <ul className="space-y-2 text-sm">
            {(candidati.dati ?? []).map((c) => {
              const chiave = `${c.workflow}:${c.tipo}:${c.campo}`;
              return (
                <li key={chiave} className="border-b border-slate-50 pb-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <Badge tono={c.occorrenze > 2 ? "giallo" : "grigio"}>×{c.occorrenze}</Badge>
                    <code className="text-slate-800">{c.campo}</code>
                    <span className="text-xs text-slate-500">
                      {c.tipo} · {c.workflow ?? "nessun workflow"}
                    </span>
                    {c.valori.length ? (
                      <span className="text-xs text-slate-400">
                        valori: {valoriDiEsempio(c.valori)}
                      </span>
                    ) : null}
                    <span className="ml-auto">
                      {apri === chiave ? (
                        <Bottone onClick={() => setApri(null)}>Annulla</Bottone>
                      ) : (
                        <Bottone onClick={() => setApri(chiave)}>Proponi un tool</Bottone>
                      )}
                    </span>
                  </div>
                  {apri === chiave ? (
                    <FormProposta
                      candidato={c}
                      campiDisponibili={campiDi(c.tipo)}
                      onFatto={() => {
                        setApri(null);
                        ricaricaTutto();
                      }}
                      onAnnulla={() => setApri(null)}
                    />
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Card titolo="Proposte di tool">
        <p className="mb-3 text-sm text-slate-600">
          Ogni proposta porta il codice, lo schema e l'<b>esito reale dei test in sandbox</b>.
          Approvare registra il tool in <code>data/tools/</code> — dato versionato, eseguito solo
          in sandbox isolata, mai importato nel processo — e fa nascere una patch di skill che
          insegna a chiamarlo, con il modello come riserva. Quella patch passa dal replay sul
          golden set e da un'approvazione a parte.
        </p>

        {proposte.errore ? <Errore>{proposte.errore}</Errore> : null}
        {proposte.inCorso ? (
          <Stato>Carico le proposte…</Stato>
        ) : (proposte.dati ?? []).length === 0 ? (
          <Stato>Nessuna proposta: parti da un candidato qui sopra.</Stato>
        ) : (
          <ul>
            {(proposte.dati ?? []).map((p) => (
              <SchedaProposta key={p.id} proposta={p} onDeciso={ricaricaTutto} />
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
