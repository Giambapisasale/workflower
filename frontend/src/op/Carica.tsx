/**
 * Carica un documento: foto o file → "Sto leggendo…" → riepilogo in tre
 * righe → "È tutto giusto?". Nessun errore bloccante, mai: qualunque
 * intoppo diventa un avviso gentile e si può riprovare.
 */

import { useEffect, useRef, useState } from "react";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  CheckCircledIcon,
  FileIcon,
  HomeIcon,
} from "@radix-ui/react-icons";
import { api, type DocumentoVista, type EsempioDoc, scaricaFile } from "../shared/api";
import { useRitorno } from "../shared/navigazione";
import { Spinner } from "../ds";
import { CardGrazie, PannelloVerdetto, RigheRiepilogo } from "./RiepilogoCard";
import { useSessione } from "./sessione";
import { TESTI } from "./testi";
import {
  BottoneFile,
  BottoneGrande,
  BottonePieno,
  Card,
  Colonna,
  Domanda,
  Indietro,
  Titolo,
} from "./ui";

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
  const torna = useRitorno("/op", "/op");
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
        <Colonna>
          <BottoneFile
            icona={ArrowUpIcon}
            primario
            accept="image/*"
            capture="environment"
            onFile={scelto}
          >
            {TESTI.fotografa}
          </BottoneFile>
          <BottoneFile icona={FileIcon} accept="application/pdf,image/*" onFile={scelto}>
            {TESTI.scegliFile}
          </BottoneFile>

          {esempi.length > 0 ? (
            <div style={{ paddingTop: 12 }}>
              <p style={{ fontSize: 17, fontWeight: 700, margin: 0 }}>
                {TESTI.scaricaEsempioTitolo}
              </p>
              <p style={{ color: "var(--text-secondary)", margin: "4px 0 14px" }}>
                {TESTI.scaricaEsempioSotto}
              </p>
              <Colonna gap={12}>
                {esempi.map((e) => (
                  <BottoneGrande
                    key={e.file}
                    icona={ArrowDownIcon}
                    onClick={() => void scaricaFile(`/samples/${e.file}`, e.file)}
                  >
                    {e.titolo}
                  </BottoneGrande>
                ))}
              </Colonna>
            </div>
          ) : null}
        </Colonna>
      ) : null}

      {fase.tipo === "cantiere" ? (
        <Colonna>
          <Domanda>{TESTI.diQualeCantiere}</Domanda>
          {cantieri.map((cantiere) => (
            <BottoneGrande
              key={cantiere.id}
              icona={HomeIcon}
              onClick={() => void invia(fase.file, cantiere.id)}
            >
              {cantiere.nome}
            </BottoneGrande>
          ))}
        </Colonna>
      ) : null}

      {fase.tipo === "attesa" ? (
        <Card>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Spinner size="sm" />
            <b>{TESTI.stoLeggendo}</b>
          </div>
          <p style={{ margin: "8px 0 0", color: "var(--text-secondary)" }}>{TESTI.puoiUscire}</p>
        </Card>
      ) : null}

      {fase.tipo === "esito" ? (
        fase.doc.riepilogo && fase.doc.semaforo !== "rosso" ? (
          <Card>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ display: "flex", flex: "0 0 18px", color: "var(--color-success)" }}>
                <CheckCircledIcon width={18} height={18} />
              </span>
              <b style={{ flex: 1 }}>{TESTI.hoLetto(fase.doc.riepilogo.tipo)}</b>
            </div>
            <RigheRiepilogo riepilogo={fase.doc.riepilogo} />
            <PannelloVerdetto doc={fase.doc} onGrazie={() => setFase({ tipo: "grazie" })} />
          </Card>
        ) : (
          <Card>
            <b>{TESTI.grazie}</b>
            <p style={{ margin: "6px 0 0", color: "var(--text-secondary)" }}>
              {fase.doc.messaggio}
            </p>
            <div style={{ marginTop: 16 }}>
              <BottoneGrande icona={HomeIcon} onClick={torna}>
                {TESTI.tornaHome}
              </BottoneGrande>
            </div>
          </Card>
        )
      ) : null}

      {fase.tipo === "grazie" ? <CardGrazie onHome={torna} /> : null}

      {fase.tipo === "avviso" ? (
        <Card>
          <b>{fase.messaggio}</b>
          <div style={{ marginTop: 16 }}>
            <Colonna gap={12}>
              <BottonePieno onClick={() => setFase({ tipo: "scegli" })}>
                {TESTI.riprova}
              </BottonePieno>
              <BottoneGrande icona={HomeIcon} onClick={torna}>
                {TESTI.tornaHome}
              </BottoneGrande>
            </Colonna>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
