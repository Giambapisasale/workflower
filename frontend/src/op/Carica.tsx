/**
 * Carica un documento: foto o file → "Sto leggendo…" → riepilogo in tre
 * righe → "È tutto giusto?". Nessun errore bloccante, mai: qualunque
 * intoppo diventa un avviso gentile e si può riprovare.
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type DocumentoVista, type EsempioDoc, scaricaFile } from "../shared/api";
import { CardGrazie, PannelloVerdetto, RigheRiepilogo } from "./RiepilogoCard";
import { useSessione } from "./sessione";
import { TESTI } from "./testi";
import { Bottone, BottoneFile, Card, Indietro, Titolo } from "./ui";

const RITMO_ATTESA_MS = 1500;
const MAX_GIRI_ATTESA = 80; // ~2 minuti, poi si rimanda a "I miei documenti"

type Fase =
  | { tipo: "scegli" }
  | { tipo: "cantiere"; file: File }
  | { tipo: "attesa" }
  | { tipo: "esito"; doc: DocumentoVista }
  | { tipo: "grazie" }
  | { tipo: "avviso"; messaggio: string };

const pausa = (ms: number) => new Promise((fine) => setTimeout(fine, ms));

export default function Carica() {
  const { sessione } = useSessione();
  const naviga = useNavigate();
  const cantieri = sessione.utente.cantieri;
  const [fase, setFase] = useState<Fase>({ tipo: "scegli" });
  const [esempi, setEsempi] = useState<EsempioDoc[]>([]);
  const vivo = useRef(true);
  useEffect(() => {
    vivo.current = true;
    api.esempi().then((e) => vivo.current && setEsempi(e)).catch(() => undefined);
    return () => {
      vivo.current = false;
    };
  }, []);

  function scelto(file: File | null) {
    if (!file) return;
    if (cantieri.length > 1) setFase({ tipo: "cantiere", file });
    else void invia(file, cantieri[0]?.id ?? null);
  }

  async function invia(file: File, cantiereId: string | null) {
    setFase({ tipo: "attesa" });
    try {
      const esito = await api.carica(file, cantiereId);
      if (!esito.doc_id) {
        setFase({ tipo: "avviso", messaggio: esito.messaggio ?? TESTI.nonRiesco });
        return;
      }
      await attendi(esito.doc_id);
    } catch {
      if (vivo.current) setFase({ tipo: "avviso", messaggio: TESTI.nonRiesco });
    }
  }

  async function attendi(id: string) {
    for (let giro = 0; giro < MAX_GIRI_ATTESA; giro += 1) {
      const doc = await api.documento(id);
      if (!vivo.current) return;
      if (!doc.in_corso) {
        setFase({ tipo: "esito", doc });
        return;
      }
      await pausa(RITMO_ATTESA_MS);
      if (!vivo.current) return;
    }
    setFase({ tipo: "avviso", messaggio: TESTI.staAncoraLavorando });
  }

  return (
    <div>
      <Indietro a="/op" />
      <Titolo>{TESTI.titoloCarica}</Titolo>

      {fase.tipo === "scegli" ? (
        <div className="space-y-4">
          <BottoneFile
            icona="📷"
            variante="primario"
            accept="image/*"
            capture="environment"
            onFile={scelto}
          >
            {TESTI.fotografa}
          </BottoneFile>
          <BottoneFile icona="📁" accept="application/pdf,image/*" onFile={scelto}>
            {TESTI.scegliFile}
          </BottoneFile>

          {esempi.length > 0 ? (
            <div className="pt-4">
              <p className="text-[17px] font-bold">{TESTI.scaricaEsempioTitolo}</p>
              <p className="mb-3 text-neutral-600">{TESTI.scaricaEsempioSotto}</p>
              <div className="space-y-3">
                {esempi.map((e) => (
                  <Bottone
                    key={e.file}
                    icona="⬇️"
                    onClick={() => void scaricaFile(`/samples/${e.file}`, e.file)}
                  >
                    {e.titolo}
                  </Bottone>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {fase.tipo === "cantiere" ? (
        <div className="space-y-4">
          <p className="text-[19px] font-bold">{TESTI.diQualeCantiere}</p>
          {cantieri.map((cantiere) => (
            <Bottone
              key={cantiere.id}
              icona="🏗️"
              onClick={() => void invia(fase.file, cantiere.id)}
            >
              {cantiere.nome}
            </Bottone>
          ))}
        </div>
      ) : null}

      {fase.tipo === "attesa" ? (
        <Card>
          ⏳ <b>{TESTI.stoLeggendo}</b>
          <p className="mt-1 text-neutral-600">{TESTI.puoiUscire}</p>
        </Card>
      ) : null}

      {fase.tipo === "esito" ? (
        fase.doc.riepilogo && fase.doc.semaforo !== "rosso" ? (
          <Card>
            ✅ <b>{TESTI.hoLetto(fase.doc.riepilogo.tipo)}</b>
            <RigheRiepilogo riepilogo={fase.doc.riepilogo} />
            <PannelloVerdetto doc={fase.doc} onGrazie={() => setFase({ tipo: "grazie" })} />
          </Card>
        ) : (
          <Card>
            🤝 <b>{TESTI.grazie}</b>
            <p className="mt-1 text-neutral-600">{fase.doc.messaggio}</p>
            <div className="mt-4">
              <Bottone icona="🏠" onClick={() => naviga("/op")}>
                {TESTI.tornaHome}
              </Bottone>
            </div>
          </Card>
        )
      ) : null}

      {fase.tipo === "grazie" ? <CardGrazie onHome={() => naviga("/op")} /> : null}

      {fase.tipo === "avviso" ? (
        <Card>
          <b>{fase.messaggio}</b>
          <div className="mt-4 space-y-3">
            <Bottone variante="primario" onClick={() => setFase({ tipo: "scegli" })}>
              {TESTI.riprova}
            </Bottone>
            <Bottone icona="🏠" onClick={() => naviga("/op")}>
              {TESTI.tornaHome}
            </Bottone>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
