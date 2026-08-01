/** L'azienda che usa il sistema: denominazione, indirizzo, partita IVA.
 *
 * Serve a rispondere a una domanda che finora nessuno poneva — la fattura che
 * stiamo leggendo è davvero intestata a noi? — quindi la pagina spiega a cosa
 * servono i campi invece di limitarsi a raccoglierli.
 *
 * È dato in `data/config/azienda.json`: ogni salvataggio è un commit nel repo
 * dati, con dentro chi l'ha fatto.
 */

import { useCallback, useEffect, useState } from "react";
import type { Azienda as DatiConfigurati, DatiAzienda } from "./api";
import { admin } from "./api";
import { Bottone, Card, Errore, IntestazionePagina, Stato } from "./ui";

const VUOTA: DatiAzienda = { denominazione: "", indirizzo: "", partita_iva: "" };

const CAMPI: { chiave: keyof DatiAzienda; etichetta: string; aiuto: string }[] = [
  {
    chiave: "denominazione",
    etichetta: "Denominazione",
    aiuto: "Come compare intestata sui documenti che ricevete.",
  },
  {
    chiave: "indirizzo",
    etichetta: "Indirizzo",
    aiuto: "Sede legale, come la scrivono i fornitori in fattura.",
  },
  {
    chiave: "partita_iva",
    etichetta: "Partita IVA",
    aiuto: "Il modo più sicuro di riconoscervi quando la ragione sociale è abbreviata.",
  },
];

export default function Azienda() {
  const [salvata, setSalvata] = useState<DatiConfigurati | null>(null);
  const [form, setForm] = useState<DatiAzienda>(VUOTA);
  const [inCorso, setInCorso] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [errore, setErrore] = useState<string | null>(null);
  const [esito, setEsito] = useState<string | null>(null);

  const carica = useCallback(async () => {
    setInCorso(true);
    setErrore(null);
    try {
      const dati = await admin.azienda();
      setSalvata(dati);
      setForm({
        denominazione: dati.denominazione,
        indirizzo: dati.indirizzo,
        partita_iva: dati.partita_iva,
      });
    } catch (e) {
      setErrore(e instanceof Error ? e.message : "Errore di rete");
    } finally {
      setInCorso(false);
    }
  }, []);

  useEffect(() => {
    carica();
  }, [carica]);

  async function salva() {
    setSalvando(true);
    setErrore(null);
    setEsito(null);
    try {
      const dati = await admin.salvaAzienda(form);
      setSalvata(dati);
      setEsito("Salvato.");
    } catch (e) {
      setErrore(e instanceof Error ? e.message : "Errore di rete");
    } finally {
      setSalvando(false);
    }
  }

  const modificato =
    salvata !== null &&
    CAMPI.some(({ chiave }) => (form[chiave] ?? "") !== (salvata[chiave] ?? ""));

  return (
    <>
      <IntestazionePagina titolo="La nostra azienda" />

      <Card titolo="Dati dell'azienda">
        {inCorso ? (
          <Stato>Carico…</Stato>
        ) : (
          <div className="grid max-w-xl gap-4">
            <p className="text-sm text-slate-500">
              Questi dati dicono al sistema chi siamo: servono a controllare che le
              fatture che arrivano siano intestate a noi e non a qualcun altro.
            </p>

            {CAMPI.map(({ chiave, etichetta, aiuto }) => (
              <label key={chiave} className="text-sm text-slate-700">
                {etichetta}
                <input
                  value={form[chiave]}
                  onChange={(e) => setForm({ ...form, [chiave]: e.target.value })}
                  className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
                />
                <span className="mt-1 block text-xs text-slate-500">{aiuto}</span>
              </label>
            ))}

            {salvata && !salvata.configurata ? (
              <p className="text-sm text-amber-700">
                Finché manca la denominazione, il controllo del destinatario non viene fatto.
              </p>
            ) : null}

            <div className="flex items-center gap-3">
              <Bottone variante="primario" onClick={salva} disabled={salvando || !modificato}>
                {salvando ? "Salvo…" : "Salva"}
              </Bottone>
              {esito && !modificato ? (
                <span className="text-sm text-slate-500">{esito}</span>
              ) : null}
            </div>

            {errore ? <Errore>{errore}</Errore> : null}
          </div>
        )}
      </Card>
    </>
  );
}
