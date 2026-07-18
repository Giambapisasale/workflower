/** "I miei documenti": elenco a semaforo 🟢🟡🔴, tap per il dettaglio. */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type DocumentoVista } from "../shared/api";
import { PALLINO, quandoLeggibile, TESTI } from "./testi";
import { Card, Indietro, Titolo } from "./ui";

export default function Documenti() {
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
        <p className="text-neutral-500">{TESTI.caricamento}</p>
      ) : documenti.length === 0 ? (
        <Card>{TESTI.nessunDocumento}</Card>
      ) : (
        <div>
          {documenti.map((doc) => (
            <Link
              key={doc.id}
              to={`/op/documenti/${doc.id}`}
              className="mb-3 flex min-h-[64px] items-center gap-3 rounded-2xl border-2 border-neutral-300 p-4 active:bg-neutral-100"
            >
              <span className="text-2xl">{PALLINO[doc.semaforo]}</span>
              <span>
                <b>{doc.titolo}</b> · {quandoLeggibile(doc.quando)}
                <span className="block text-neutral-500">{doc.messaggio}</span>
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
