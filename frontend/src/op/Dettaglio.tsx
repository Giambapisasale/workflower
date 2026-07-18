/** Dettaglio semplificato di un documento; da qui si può ancora dire la propria. */

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, type DocumentoVista } from "../shared/api";
import { CardGrazie, PannelloVerdetto, RigheRiepilogo } from "./RiepilogoCard";
import { PALLINO, quandoLeggibile, TESTI } from "./testi";
import { Card, Indietro, Titolo } from "./ui";

const RITMO_ATTESA_MS = 2000;

export default function Dettaglio() {
  const { id } = useParams();
  const naviga = useNavigate();
  const [doc, setDoc] = useState<DocumentoVista | null>(null);
  const [avviso, setAvviso] = useState<string | null>(null);
  const [grazie, setGrazie] = useState(false);

  useEffect(() => {
    if (!id) return;
    let vivo = true;
    let timer: number | undefined;
    const aggiorna = () => {
      api
        .documento(id)
        .then((fresco) => {
          if (!vivo) return;
          setDoc(fresco);
          // finché il sistema ci lavora, la pagina si aggiorna da sola
          if (fresco.in_corso) timer = window.setTimeout(aggiorna, RITMO_ATTESA_MS);
        })
        .catch(() => vivo && setAvviso(TESTI.nonTrovato));
    };
    aggiorna();
    return () => {
      vivo = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [id]);

  return (
    <div>
      <Indietro a="/op/documenti" />
      {avviso ? (
        <Card>
          <b>{avviso}</b>
        </Card>
      ) : doc === null ? (
        <p className="text-neutral-500">{TESTI.caricamento}</p>
      ) : grazie ? (
        <CardGrazie onHome={() => naviga("/op/documenti")} />
      ) : (
        <div>
          <Titolo>{doc.titolo}</Titolo>
          <Card>
            <div className="flex items-center gap-2">
              <span className="text-2xl">{PALLINO[doc.semaforo]}</span>
              <b>{doc.messaggio}</b>
            </div>
            <p className="mt-1 text-neutral-500">
              Caricato {quandoLeggibile(doc.quando)}
            </p>
            {doc.riepilogo ? <RigheRiepilogo riepilogo={doc.riepilogo} /> : null}
            {doc.riepilogo && !doc.chiuso && !doc.in_corso ? (
              <PannelloVerdetto doc={doc} onGrazie={() => setGrazie(true)} />
            ) : null}
          </Card>
        </div>
      )}
    </div>
  );
}
