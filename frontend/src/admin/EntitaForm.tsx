/** Crea/modifica una voce a mano (M13), con il form generato dallo schema. */

import { type FormEvent, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ErroreApi } from "../shared/api";
import { admin } from "./api";
import CampiSchema from "./CampiSchema";
import { useCarica } from "./formato";
import { caricaMetaForm } from "./metaForm";
import { Bottone, Card, Errore, Stato } from "./ui";

export default function EntitaForm() {
  const { tipo = "", id } = useParams();
  const nuovo = !id;
  const navigate = useNavigate();

  const { dati: setup, errore, inCorso } = useCarica(async () => {
    const meta = await caricaMetaForm(tipo);
    // In creazione si parte da un oggetto vuoto: CampiSchema genera comunque
    // tutti i campi dallo schema (non dalle chiavi presenti nel valore).
    const iniziale = id ? (await admin.entitiesGet(tipo, id)).dati : {};
    return { ...meta, iniziale };
  }, [tipo, id]);

  const [valore, setValore] = useState<Record<string, unknown>>({});
  const [salvando, setSalvando] = useState(false);
  const [erroreSalva, setErroreSalva] = useState<string | null>(null);

  useEffect(() => {
    if (setup) setValore(setup.iniziale as Record<string, unknown>);
  }, [setup]);

  if (inCorso) return <Stato>Carico…</Stato>;
  if (errore || !setup) return <Errore>{errore ?? "Non trovato"}</Errore>;
  const { metaTipo, etichette, opzioni } = setup;

  async function salva(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    setErroreSalva(null);
    try {
      if (nuovo) await admin.entitiesCrea(tipo, valore);
      else await admin.entitiesAggiorna(tipo, id!, valore);
      navigate(`/admin/dati/${tipo}`);
    } catch (err) {
      setErroreSalva(err instanceof ErroreApi ? err.message : "Errore di salvataggio");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <form onSubmit={salva}>
      <div className="mb-4 flex items-center gap-3">
        <button
          type="button"
          onClick={() => navigate(`/admin/dati/${tipo}`)}
          className="text-slate-400 hover:text-slate-700"
        >
          ← {metaTipo.etichetta}
        </button>
        <h1 className="text-lg font-bold">
          {nuovo ? `Nuovo · ${metaTipo.etichetta}` : `Modifica · ${id}`}
        </h1>
      </div>

      <Card>
        <CampiSchema
          schema={metaTipo.schema}
          valore={valore}
          onChange={setValore}
          riferimenti={metaTipo.riferimenti}
          opzioni={opzioni}
          etichette={etichette}
        />
      </Card>

      {erroreSalva ? <Errore>{erroreSalva}</Errore> : null}

      <div className="mt-4 flex gap-2">
        <Bottone variante="primario" type="submit" disabled={salvando}>
          {salvando ? "Salvo…" : "Salva"}
        </Bottone>
        <Bottone onClick={() => navigate(`/admin/dati/${tipo}`)}>Annulla</Bottone>
      </div>
    </form>
  );
}
