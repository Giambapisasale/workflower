/** Crea/modifica una voce a mano (M13), con il form generato dallo schema. */

import { type FormEvent, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ErroreApi } from "../shared/api";
import { admin } from "./api";
import CampiSchema from "./CampiSchema";
import { useCarica } from "./formato";
import { caricaMetaForm } from "./metaForm";
import { useRitorno } from "./provenienza";
import { Bottone, Card, Errore, IntestazionePagina, Stato } from "./ui";

export default function EntitaForm() {
  const { tipo = "", id } = useParams();
  const nuovo = !id;
  // Qui si arriva anche dal Cruscotto o dalla Contabilità: salva e annulla
  // riportano lì, non per forza alla lista del tipo.
  const esci = useRitorno(`/admin/dati/${tipo}`);

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
      esci();
    } catch (err) {
      setErroreSalva(err instanceof ErroreApi ? err.message : "Errore di salvataggio");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <form onSubmit={salva}>
      <IntestazionePagina
        titolo={nuovo ? `Nuovo · ${metaTipo.etichetta}` : `Modifica · ${id}`}
        indietro={`/admin/dati/${tipo}`}
        etichettaIndietro={metaTipo.etichetta}
      />

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

      <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
        <Bottone variante="primario" type="submit" disabled={salvando}>
          {salvando ? "Salvo…" : "Salva"}
        </Bottone>
        <Bottone onClick={esci}>Annulla</Bottone>
      </div>
    </form>
  );
}
