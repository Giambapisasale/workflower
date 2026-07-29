/** Elenco gestibile di un tipo entità (M13): nuovo, modifica, elimina. */

import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ErroreApi } from "../shared/api";
import { admin } from "./api";
import { useCarica } from "./formato";
import {
  Badge,
  Bottone,
  Card,
  Errore,
  IntestazionePagina,
  MONO,
  Stato,
  Tabella,
} from "./ui";
import type { TableColumn, TableRow } from "../ds";

function statoBadge(stato: string) {
  const tono = stato === "validato" ? "verde" : stato === "errore" ? "rosso" : "giallo";
  return <Badge tono={tono}>{stato}</Badge>;
}

type RigaVoce = TableRow & { titolo: string | null; stato: string };

export default function EntitaLista() {
  const { tipo = "" } = useParams();
  const { dati, errore, inCorso, ricarica } = useCarica(async () => {
    const [tipi, voci] = await Promise.all([admin.entitiesMeta(), admin.entitiesLista(tipo)]);
    return { metaTipo: tipi.find((t) => t.tipo === tipo), voci };
  }, [tipo]);

  const [conferma, setConferma] = useState<string | null>(null);
  const [erroreElimina, setErroreElimina] = useState<string | null>(null);
  const [inElimina, setInElimina] = useState(false);

  if (inCorso) return <Stato>Carico…</Stato>;
  if (errore || !dati) return <Errore>{errore ?? "Non trovato"}</Errore>;
  const etichetta = dati.metaTipo?.etichetta ?? tipo;

  async function elimina(id: string) {
    setInElimina(true);
    setErroreElimina(null);
    try {
      await admin.entitiesElimina(tipo, id);
      setConferma(null);
      ricarica();
    } catch (e) {
      setErroreElimina(e instanceof ErroreApi ? e.message : "Errore nell'eliminazione");
    } finally {
      setInElimina(false);
    }
  }

  const colonne: TableColumn<RigaVoce>[] = [
    {
      title: "Codice",
      dataIndex: "id",
      render: (_v, r) => (
        <span style={{ ...MONO, fontSize: 12, color: "var(--text-secondary)" }}>{r.id}</span>
      ),
    },
    {
      title: "Descrizione",
      dataIndex: "titolo",
      render: (_v, r) => <b>{r.titolo ?? "—"}</b>,
    },
    { title: "Stato", dataIndex: "stato", render: (_v, r) => statoBadge(r.stato) },
    {
      title: "Azioni",
      dataIndex: "azioni",
      render: (_v, r) => {
        const id = String(r.id);
        if (conferma === id) {
          return (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>Eliminare?</span>
              <Bottone variante="pericolo" onClick={() => elimina(id)} disabled={inElimina}>
                Sì, elimina
              </Bottone>
              <Bottone onClick={() => setConferma(null)}>No</Bottone>
            </span>
          );
        }
        return (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
            <Link to={`/admin/dati/${tipo}/${id}`} style={{ fontSize: 12, fontWeight: 700 }}>
              Modifica
            </Link>
            <Bottone
              variante="pericolo"
              onClick={() => {
                setConferma(id);
                setErroreElimina(null);
              }}
            >
              Elimina
            </Bottone>
          </span>
        );
      },
    },
  ];

  return (
    <>
      <IntestazionePagina
        titolo={etichetta}
        indietro="/admin/dati"
        etichettaIndietro="Dati"
        accanto={dati.voci.length}
        azioni={
          <Link to={`/admin/dati/${tipo}/nuovo`}>
            <Bottone variante="primario">+ Nuovo</Bottone>
          </Link>
        }
      />

      {erroreElimina ? <div style={{ marginBottom: 16 }}><Errore>{erroreElimina}</Errore></div> : null}

      <Card>
        {dati.voci.length === 0 ? (
          <Stato>Ancora niente. Usa “+ Nuovo”.</Stato>
        ) : (
          <Tabella
            colonne={colonne}
            righe={dati.voci.map((v) => ({ ...v }) as RigaVoce)}
            righePerPagina={25}
          />
        )}
      </Card>
    </>
  );
}
