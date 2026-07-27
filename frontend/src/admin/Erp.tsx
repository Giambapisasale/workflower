/** Sincronizzazioni ERP (piano ERP, M28): registro, arretrati e recupero manuale.
 *
 * Il flusso normale è automatico — un documento validato va a valle da sé — quindi
 * qui si guarda solo quando qualcosa non è arrivato: l'elenco dei documenti rimasti
 * indietro con il pulsante «riprova», e il registro degli ultimi tentativi con il
 * motivo dei fallimenti. Nulla si sincronizza all'insaputa dell'ufficio.
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { ErpStato } from "./api";
import { admin } from "./api";
import { dataBreve } from "./formato";
import { Badge, Bottone, Card, Errore, Kpi, Stato } from "./ui";

export default function Erp() {
  const [stato, setStato] = useState<ErpStato | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [inCorso, setInCorso] = useState(true);
  const [azione, setAzione] = useState<string | null>(null); // id dell'azione in corso
  const [esito, setEsito] = useState<string | null>(null);

  const carica = useCallback(async () => {
    setInCorso(true);
    setErrore(null);
    try {
      setStato(await admin.erpStato());
    } catch (e) {
      setErrore(e instanceof Error ? e.message : "Errore di rete");
    } finally {
      setInCorso(false);
    }
  }, []);

  useEffect(() => {
    carica();
  }, [carica]);

  const agisci = useCallback(
    async (chiave: string, fn: () => Promise<string>) => {
      setAzione(chiave);
      setEsito(null);
      setErrore(null);
      try {
        setEsito(await fn());
        await carica();
      } catch (e) {
        setErrore(e instanceof Error ? e.message : "Errore di rete");
      } finally {
        setAzione(null);
      }
    },
    [carica],
  );

  const risincronizzaTutti = () =>
    agisci("tutti", async () => {
      const r = await admin.erpRisincronizza();
      if (r.tentate === 0) return "Non c'era nulla da re-inviare.";
      const coda = r.interrotto
        ? " Interrotto: l'ERP sembra non raggiungibile, riprova più tardi."
        : "";
      return `Re-inviati ${r.ok} documenti su ${r.tentate} (errori: ${r.errori}).${coda}`;
    });

  const risincronizzaUno = (id: string) =>
    agisci(id, async () => {
      const r = await admin.erpRisincronizzaUno(id);
      if (r.esito === "ok") return `${id} è arrivato a destinazione (${r.erp_id}).`;
      return `${id} non è passato: ${r.errore || r.motivo || r.esito}`;
    });

  const rileggiPagamenti = () =>
    agisci("pagamenti", async () => {
      const r = await admin.erpRileggiPagamenti();
      if (r.esito !== "ok") return "L'integrazione contabile non è configurata.";
      return `Stato pagamenti aggiornato: ${r.creati} nuovi, ${r.aggiornati} aggiornati (errori: ${r.errori}).`;
    });

  if (errore && stato === null) return <Errore>{errore}</Errore>;
  if (inCorso && stato === null) return <Stato>Carico lo stato delle sincronizzazioni…</Stato>;
  if (stato === null) return null;

  const arretrati = stato.da_sincronizzare;
  const tentativi = [...stato.ultimi_tentativi].reverse();
  const occupato = azione !== null;

  return (
    <>
      <Card
        titolo="Sincronizzazioni verso la contabilità"
        azioni={
          stato.erp_attivo ? (
            <div className="flex gap-2">
              <Bottone disabled={occupato} onClick={rileggiPagamenti}>
                {azione === "pagamenti" ? "Rileggo…" : "Rileggi i pagamenti"}
              </Bottone>
              <Bottone
                variante="primario"
                disabled={occupato || arretrati.length === 0}
                onClick={risincronizzaTutti}
              >
                {azione === "tutti" ? "Re-invio…" : "Re-invia gli arretrati"}
              </Bottone>
            </div>
          ) : null
        }
      >
        {!stato.erp_attivo ? (
          <p className="text-sm text-slate-600">
            L'integrazione con la contabilità è <strong>spenta</strong>: Workflower funziona
            normalmente, i documenti validati restano qui e non vengono inviati a valle. Per
            accenderla vanno configurate le credenziali dell'ERP (vedi <code>docs/erp-poc.md</code>).
          </p>
        ) : (
          <>
            <p className="text-sm text-slate-600">
              I documenti validati vengono inviati alla contabilità da soli. Se l'ERP era
              momentaneamente irraggiungibile qualcuno può restare indietro: compare qui sotto e
              si re-invia con un clic. Ogni tentativo, riuscito o no, resta nel registro.
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              {Object.entries(stato.per_tipo).map(([tipo, c]) => (
                <Kpi
                  key={tipo}
                  etichetta={tipo === "ddt" ? "DDT" : tipo}
                  valore={`${c.sincronizzate}/${c.validate}`}
                  nota={
                    c.da_sincronizzare > 0
                      ? `${c.da_sincronizzare} da re-inviare`
                      : "tutti a destinazione"
                  }
                />
              ))}
            </div>
          </>
        )}
        {esito ? <p className="mt-4 text-sm font-medium text-slate-700">{esito}</p> : null}
        {errore ? <div className="mt-4"><Errore>{errore}</Errore></div> : null}
      </Card>

      {stato.erp_attivo ? (
        <Card titolo={`Rimasti indietro (${arretrati.length})`}>
          {arretrati.length === 0 ? (
            <Stato>Nessun documento in attesa: la contabilità è allineata.</Stato>
          ) : (
            <ul className="divide-y divide-slate-100">
              {arretrati.map((d) => (
                <li key={d.id} className="flex items-center justify-between gap-3 py-2">
                  <span className="flex items-center gap-2">
                    <Link
                      to={`/admin/dati/${d.tipo}/${d.id}`}
                      className="font-mono text-sm text-sky-700 hover:underline"
                    >
                      {d.id}
                    </Link>
                    <Badge tono="grigio">{d.tipo === "ddt" ? "DDT" : d.tipo}</Badge>
                  </span>
                  <Bottone disabled={occupato} onClick={() => risincronizzaUno(d.id)}>
                    {azione === d.id ? "Invio…" : "Riprova"}
                  </Bottone>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ) : null}

      <Card titolo="Registro dei tentativi">
        {tentativi.length === 0 ? (
          <Stato>Nessun tentativo registrato.</Stato>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                  <th className="pb-2 pr-4">Quando</th>
                  <th className="pb-2 pr-4">Documento</th>
                  <th className="pb-2 pr-4">Esito</th>
                  <th className="pb-2">In contabilità / motivo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {tentativi.map((t, i) => (
                  <tr key={`${t.ts}-${t.entity_id}-${i}`} className="align-top">
                    <td className="py-2 pr-4 whitespace-nowrap text-slate-500">
                      {dataBreve(t.ts)}
                    </td>
                    <td className="py-2 pr-4 font-mono text-xs text-slate-600">{t.entity_id}</td>
                    <td className="py-2 pr-4">
                      <Badge tono={t.esito === "ok" ? "verde" : "rosso"}>
                        {t.esito === "ok" ? "arrivato" : "non passato"}
                      </Badge>
                    </td>
                    <td className="py-2 text-slate-600">
                      {t.esito === "ok" ? (
                        <span className="font-mono text-xs">{t.erp_id}</span>
                      ) : (
                        <span className="text-xs text-red-700">{t.errore}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
