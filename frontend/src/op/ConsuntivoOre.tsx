/**
 * "Le mie ore": l'operaio segna le ore fatte, un passo alla volta —
 * giorno → cantiere → quante ore → cosa hai fatto → conferma. Nessun form,
 * bottoni grandi. Le ore vanno in ufficio per il controllo; la paga oraria
 * non si tocca qui, arriva dal profilo del dipendente.
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CalendarIcon, CheckIcon, HomeIcon } from "@radix-ui/react-icons";
import {
  api,
  type AttivitaScelta,
  type Cantiere,
  type ConsuntivoContesto,
} from "../shared/api";
import { Button, Input, Spinner, Step, Stepper } from "../ds";
import { TESTI, dataBreve } from "./testi";
import {
  BottoneGrande,
  BottonePieno,
  Card,
  Colonna,
  Domanda,
  Indietro,
  Spiegazione,
  Titolo,
} from "./ui";

const ORE_MIN = 0.5;
const ORE_MAX = 16;
const ORE_PASSO = 0.5;

function isoLocale(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const g = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${g}`;
}

type Fase =
  | { tipo: "carica" }
  | { tipo: "nessuno" }
  | { tipo: "giorno" }
  | { tipo: "cantiere" }
  | { tipo: "ore" }
  | { tipo: "attivita" }
  | { tipo: "conferma" }
  | { tipo: "invio" }
  | { tipo: "inviato" }
  | { tipo: "avviso"; messaggio: string };

/** A quale pallino dello Stepper corrisponde ogni passo. */
const PASSO_STEPPER: Partial<Record<Fase["tipo"], number>> = {
  giorno: 0,
  cantiere: 1,
  ore: 2,
  attivita: 3,
  conferma: 3,
};

export default function ConsuntivoOre() {
  const naviga = useNavigate();
  const oggi = isoLocale(new Date());
  const ieri = isoLocale(new Date(Date.now() - 86_400_000));

  const [fase, setFase] = useState<Fase>({ tipo: "carica" });
  const [contesto, setContesto] = useState<ConsuntivoContesto | null>(null);
  const [data, setData] = useState(oggi);
  const [cantiere, setCantiere] = useState<Cantiere | null>(null);
  const [ore, setOre] = useState(8);
  const [scelte, setScelte] = useState<Set<string>>(new Set());
  const [nota, setNota] = useState("");
  const vivo = useRef(true);

  useEffect(() => {
    vivo.current = true;
    api
      .consuntivoContesto(oggi)
      .then((c) => {
        if (!vivo.current) return;
        setContesto(c);
        setFase(c.dipendente ? { tipo: "giorno" } : { tipo: "nessuno" });
      })
      .catch(() => vivo.current && setFase({ tipo: "avviso", messaggio: TESTI.oreErrore }));
    return () => {
      vivo.current = false;
    };
  }, [oggi]);

  async function scegliGiorno(giorno: string) {
    setData(giorno);
    setFase({ tipo: "carica" });
    try {
      const c = await api.consuntivoContesto(giorno);
      if (!vivo.current) return;
      setContesto(c);
      if (c.cantieri.length === 0) {
        setFase({ tipo: "avviso", messaggio: TESTI.oreNessunCantiere });
      } else if (c.cantieri.length === 1) {
        setCantiere(c.cantieri[0]);
        setFase({ tipo: "ore" });
      } else {
        setFase({ tipo: "cantiere" });
      }
    } catch {
      if (vivo.current) setFase({ tipo: "avviso", messaggio: TESTI.oreErrore });
    }
  }

  function alterna(id: string) {
    setScelte((prima) => {
      const dopo = new Set(prima);
      if (dopo.has(id)) dopo.delete(id);
      else dopo.add(id);
      return dopo;
    });
  }

  async function invia() {
    if (!cantiere) return;
    setFase({ tipo: "invio" });
    const attivita: AttivitaScelta[] = [
      ...[...scelte].map((id) => ({ lavorazione_id: id })),
      ...(nota.trim() ? [{ descrizione: nota.trim() }] : []),
    ];
    try {
      await api.inviaConsuntivo({ cantiere_id: cantiere.id, data, ore, attivita });
      if (vivo.current) setFase({ tipo: "inviato" });
    } catch {
      if (vivo.current) setFase({ tipo: "avviso", messaggio: TESTI.oreErrore });
    }
  }

  const quando = data === oggi ? TESTI.oggi : data === ieri ? TESTI.ieri : dataBreve(data);
  const passo = PASSO_STEPPER[fase.tipo];
  const scelteDescritte = [
    ...(contesto?.attivita_disponibili ?? [])
      .filter((a) => scelte.has(a.id))
      .map((a) => a.descrizione),
    ...(nota.trim() ? [nota.trim()] : []),
  ];

  return (
    <div>
      <Indietro onClick={() => naviga("/op")} />
      <Titolo>{TESTI.titoloOre}</Titolo>

      {passo !== undefined ? (
        <div style={{ marginBottom: 24 }}>
          <Stepper index={passo}>
            <Step>Giorno</Step>
            <Step>Cantiere</Step>
            <Step>Ore</Step>
            <Step>Attività</Step>
          </Stepper>
        </div>
      ) : null}

      {fase.tipo === "carica" || fase.tipo === "invio" ? (
        <Card>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Spinner size="sm" />
            <span>{TESTI.caricamento}</span>
          </div>
        </Card>
      ) : null}

      {fase.tipo === "nessuno" ? (
        <Card>
          <b>{TESTI.oreNessunDip}</b>
          <div style={{ marginTop: 16 }}>
            <BottoneGrande icona={HomeIcon} onClick={() => naviga("/op")}>
              {TESTI.tornaHome}
            </BottoneGrande>
          </div>
        </Card>
      ) : null}

      {fase.tipo === "giorno" ? (
        <Colonna>
          <Domanda>{TESTI.oreQuando}</Domanda>
          <BottoneGrande primario icona={CalendarIcon} onClick={() => void scegliGiorno(oggi)}>
            {TESTI.oggi}
          </BottoneGrande>
          <BottoneGrande icona={CalendarIcon} onClick={() => void scegliGiorno(ieri)}>
            {TESTI.ieri}
          </BottoneGrande>
        </Colonna>
      ) : null}

      {fase.tipo === "cantiere" ? (
        <Colonna>
          <Domanda>{TESTI.oreQualeCantiere}</Domanda>
          {(contesto?.cantieri ?? []).map((c) => (
            <BottoneGrande
              key={c.id}
              icona={HomeIcon}
              onClick={() => {
                setCantiere(c);
                setFase({ tipo: "ore" });
              }}
            >
              {c.nome}
            </BottoneGrande>
          ))}
        </Colonna>
      ) : null}

      {fase.tipo === "ore" ? (
        <Colonna gap={20}>
          <Domanda>{TESTI.oreQuante}</Domanda>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
            }}
          >
            <Button
              variant="outline"
              size="xl"
              style={{ width: 80, minHeight: 64, justifyContent: "center", fontSize: 28 }}
              disabled={ore <= ORE_MIN}
              onClick={() => setOre((o) => Math.max(ORE_MIN, o - ORE_PASSO))}
              aria-label="meno mezz'ora"
            >
              −
            </Button>
            <div style={{ fontSize: 30, fontWeight: 700 }}>{TESTI.oreUnita(ore)}</div>
            <Button
              variant="outline"
              size="xl"
              style={{ width: 80, minHeight: 64, justifyContent: "center", fontSize: 28 }}
              disabled={ore >= ORE_MAX}
              onClick={() => setOre((o) => Math.min(ORE_MAX, o + ORE_PASSO))}
              aria-label="più mezz'ora"
            >
              +
            </Button>
          </div>
          <BottonePieno onClick={() => setFase({ tipo: "attivita" })}>
            {TESTI.oreAvanti}
          </BottonePieno>
        </Colonna>
      ) : null}

      {fase.tipo === "attivita" ? (
        <Colonna>
          <Domanda>{TESTI.oreCosaTitolo}</Domanda>
          <Spiegazione>{TESTI.oreCosaSotto}</Spiegazione>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {(contesto?.attivita_disponibili ?? []).map((a) => (
              <Button
                key={a.id}
                variant={scelte.has(a.id) ? "primary" : "outline"}
                size="md"
                borderRadius="pills"
                compact
                style={{ minHeight: 44, padding: "0 16px" }}
                onClick={() => alterna(a.id)}
              >
                {a.descrizione}
              </Button>
            ))}
          </div>
          <Input
            value={nota}
            onChange={(e) => setNota(e.target.value)}
            placeholder={TESTI.oreAltro}
            style={{ width: "100%", fontSize: 18, padding: "12px 14px" }}
          />
          <BottonePieno onClick={() => setFase({ tipo: "conferma" })}>
            {scelte.size > 0 || nota.trim() ? TESTI.oreAvanti : TESTI.oreSalta}
          </BottonePieno>
        </Colonna>
      ) : null}

      {fase.tipo === "conferma" ? (
        <Colonna>
          <Domanda>{TESTI.oreConferma}</Domanda>
          <Card>
            <div style={{ fontSize: 18, fontWeight: 700 }}>{cantiere?.nome}</div>
            <div style={{ marginTop: 4, color: "var(--text-secondary)" }}>
              {quando} · {TESTI.oreUnita(ore)}
            </div>
            {scelteDescritte.length > 0 ? (
              <div style={{ marginTop: 8, color: "var(--text-secondary)" }}>
                {scelteDescritte.join(", ")}
              </div>
            ) : null}
          </Card>
          <BottoneGrande primario icona={CheckIcon} onClick={() => void invia()}>
            {TESTI.oreInvia}
          </BottoneGrande>
        </Colonna>
      ) : null}

      {fase.tipo === "inviato" ? (
        <Card>
          <b>{TESTI.oreInviato}</b>
          <p style={{ margin: "6px 0 0", color: "var(--text-secondary)" }}>
            {TESTI.oreInviatoSotto}
          </p>
          <div style={{ marginTop: 16 }}>
            <BottoneGrande icona={HomeIcon} onClick={() => naviga("/op")}>
              {TESTI.tornaHome}
            </BottoneGrande>
          </div>
        </Card>
      ) : null}

      {fase.tipo === "avviso" ? (
        <Card>
          <b>{fase.messaggio}</b>
          <div style={{ marginTop: 16 }}>
            <Colonna gap={12}>
              <BottonePieno onClick={() => setFase({ tipo: "giorno" })}>
                {TESTI.riprova}
              </BottonePieno>
              <BottoneGrande icona={HomeIcon} onClick={() => naviga("/op")}>
                {TESTI.tornaHome}
              </BottoneGrande>
            </Colonna>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
