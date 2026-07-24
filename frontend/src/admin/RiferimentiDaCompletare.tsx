/** In revisione: i riferimenti (fornitore, cantiere, …) che l'estrazione non ha
 * risolto. Per ciascuno l'ufficio può CREARE l'anagrafica mancante — precompilata
 * coi dati letti dal documento (`riferimenti_estratti`) — oppure COLLEGARNE una
 * esistente. Generico: itera i campi-riferimento del tipo, non è cablato al
 * fornitore. Nulla di questo tocca il backend: usa la CRUD entità esistente. */

import { useState } from "react";
import { ErroreApi } from "../shared/api";
import { admin, type Revisione } from "./api";
import CampiSchema from "./CampiSchema";
import { useCarica } from "./formato";
import { caricaMetaForm, type MetaForm } from "./metaForm";
import { Badge, Bottone, Card, Errore } from "./ui";

type Estratti = Record<string, Record<string, unknown>>;

function anteprima(dati: Record<string, unknown>): string {
  return (
    (dati.ragione_sociale as string) ??
    (dati.nome as string) ??
    (dati.partita_iva as string) ??
    ""
  );
}

function SottoScheda({
  rev,
  campo,
  tipoTarget,
  meta,
  onRisolto,
}: {
  rev: Revisione;
  campo: string;
  tipoTarget: string;
  meta: MetaForm;
  onRisolto: () => void;
}) {
  const [modo, setModo] = useState<null | "crea" | "collega">(null);
  const [targetMeta, setTargetMeta] = useState<MetaForm | null>(null);
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [scelto, setScelto] = useState("");
  const [inCorso, setInCorso] = useState(false);
  const [errore, setErrore] = useState<string | null>(null);

  const dati = rev.entita.dati as Record<string, unknown>;
  const estratti = (dati.riferimenti_estratti as Estratti | null) ?? {};
  const etichetta = meta.etichette[tipoTarget] ?? tipoTarget;
  const esistenti = meta.opzioni[tipoTarget] ?? [];
  const daDoc = estratti[campo] ?? {};

  async function risolviCon(id: string) {
    setInCorso(true);
    setErrore(null);
    try {
      const rest: Estratti = { ...estratti };
      delete rest[campo];
      await admin.entitiesAggiorna(rev.tipo, rev.entita.id, {
        ...dati,
        [campo]: id,
        riferimenti_estratti: Object.keys(rest).length ? rest : null,
      });
      onRisolto();
    } catch (e) {
      setErrore(e instanceof ErroreApi ? e.message : "Operazione non riuscita.");
      setInCorso(false);
    }
  }

  async function apriCrea() {
    setInCorso(true);
    setErrore(null);
    try {
      const tm = await caricaMetaForm(tipoTarget);
      setTargetMeta(tm);
      setForm({ ...daDoc });
      setModo("crea");
    } catch (e) {
      setErrore(e instanceof ErroreApi ? e.message : "Impossibile aprire il form.");
    } finally {
      setInCorso(false);
    }
  }

  async function creaEcollega() {
    setInCorso(true);
    setErrore(null);
    try {
      const { id } = await admin.entitiesCrea(tipoTarget, form);
      await risolviCon(id);
    } catch (e) {
      setErrore(e instanceof ErroreApi ? e.message : "Creazione non riuscita.");
      setInCorso(false);
    }
  }

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50/40 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tono="giallo">Manca</Badge>
        <span className="font-semibold text-slate-800">{etichetta}</span>
        {anteprima(daDoc) ? (
          <span className="text-sm text-slate-600">
            letto dal documento: <span className="font-medium">{anteprima(daDoc)}</span>
          </span>
        ) : (
          <span className="text-sm text-slate-500">nessun dato precompilabile dal documento</span>
        )}
      </div>

      {modo === null ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <Bottone variante="primario" onClick={apriCrea} disabled={inCorso}>
            {inCorso ? "Apro…" : `Crea ${etichetta} dal documento`}
          </Bottone>
          {esistenti.length > 0 ? (
            <Bottone onClick={() => setModo("collega")} disabled={inCorso}>
              Collega esistente
            </Bottone>
          ) : null}
        </div>
      ) : null}

      {modo === "collega" ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <select
            value={scelto}
            onChange={(e) => setScelto(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">— scegli —</option>
            {esistenti.map((v) => (
              <option key={v.id} value={v.id}>{v.titolo ?? v.id}</option>
            ))}
          </select>
          <Bottone
            variante="primario"
            onClick={() => scelto && risolviCon(scelto)}
            disabled={inCorso || !scelto}
          >
            {inCorso ? "Collego…" : "Collega"}
          </Bottone>
          <Bottone onClick={() => setModo(null)} disabled={inCorso}>Annulla</Bottone>
        </div>
      ) : null}

      {modo === "crea" && targetMeta ? (
        <div className="mt-3">
          <p className="mb-2 text-xs text-slate-500">
            Completa i campi obbligatori che il documento non riporta, poi crea.
          </p>
          <CampiSchema
            schema={targetMeta.schema}
            valore={form}
            onChange={setForm}
            riferimenti={targetMeta.riferimenti}
            opzioni={targetMeta.opzioni}
            etichette={targetMeta.etichette}
          />
          <div className="mt-3 flex gap-2">
            <Bottone variante="primario" onClick={creaEcollega} disabled={inCorso}>
              {inCorso ? "Creo…" : `Crea ${etichetta} e collega`}
            </Bottone>
            <Bottone onClick={() => setModo(null)} disabled={inCorso}>Annulla</Bottone>
          </div>
        </div>
      ) : null}

      {errore ? <div className="mt-2"><Errore>{errore}</Errore></div> : null}
    </div>
  );
}

export default function RiferimentiDaCompletare({
  rev,
  onRisolto,
}: {
  rev: Revisione;
  onRisolto: () => void;
}) {
  const { dati: meta, errore } = useCarica(() => caricaMetaForm(rev.tipo), [rev.tipo]);
  if (errore) return null; // il tipo non ha meta gestibile: niente card
  if (!meta) return null;

  const dati = rev.entita.dati as Record<string, unknown>;
  const mancanti = Object.entries(meta.riferimenti).filter(([campo]) => !dati[campo]);
  if (mancanti.length === 0) return null;

  return (
    <Card titolo="Riferimenti da completare">
      <p className="mb-4 text-sm text-slate-600">
        Questi riferimenti non sono stati trovati in anagrafica durante l'estrazione. Puoi
        <strong> crearli dal documento</strong> (precompilati con ciò che è stato letto) o
        collegarne uno esistente. L'anagrafica creata nasce già validata.
      </p>
      <div className="space-y-3">
        {mancanti.map(([campo, tipoTarget]) => (
          <SottoScheda
            key={campo}
            rev={rev}
            campo={campo}
            tipoTarget={tipoTarget}
            meta={meta}
            onRisolto={onRisolto}
          />
        ))}
      </div>
    </Card>
  );
}
