/** "I miei documenti": elenco a semaforo, tap per il dettaglio. */

import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type DocumentoVista } from "../shared/api";
import { quandoLeggibile, TESTI } from "./testi";
import { Card, Colonna, Indietro, Pallino, Titolo } from "./ui";

export default function Documenti() {
  const naviga = useNavigate();
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
      <Indietro onClick={() => naviga("/op")} />
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
