/** "I miei documenti": elenco a semaforo, tap per il dettaglio. */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type DocumentoVista } from "../shared/api";
import { usePercorsoCorrente } from "../shared/navigazione";
import { quandoLeggibile, TESTI } from "./testi";
import { Card, Colonna, Indietro, Pallino, Titolo } from "./ui";

export default function Documenti() {
  const da = usePercorsoCorrente();
  const [documenti, setDocumenti] = useState<DocumentoVista[] | null>(null);
  const [avviso, setAvviso] = useState<string | null>(null);

  useEffect(() => {
    api
      .documenti()
      .then(setDocumenti)
      .catch(() => setAvviso(TESTI.nonSoRispondere));
  }, []);

  return (
    <div>
      <Indietro a="/op" />
      <Titolo>{TESTI.titoloDocumenti}</Titolo>

      {avviso ? (
        <Card>
          <b>{avviso}</b>
        </Card>
      ) : documenti === null ? (
        <p style={{ color: "var(--text-secondary)" }}>{TESTI.caricamento}</p>
      ) : documenti.length === 0 ? (
        <Card>{TESTI.nessunDocumento}</Card>
      ) : (
        <Colonna gap={12}>
          {documenti.map((doc) => (
            <Link
              key={doc.id}
              to={`/op/documenti/${doc.id}`}
              state={{ da }}
              className="wf-riga-documento"
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 12,
                minHeight: 64,
                background: "var(--background-primary)",
                border: "1px solid var(--border-color)",
                borderRadius: "var(--radius)",
                padding: 14,
                color: "var(--text-primary)",
                textDecoration: "none",
              }}
            >
              <Pallino semaforo={doc.semaforo} alto />
              <span>
                <b>{doc.titolo}</b> · {quandoLeggibile(doc.quando)}
                <span style={{ display: "block", color: "var(--text-secondary)" }}>
                  {doc.messaggio}
                </span>
              </span>
            </Link>
          ))}
        </Colonna>
      )}
    </div>
  );
}
