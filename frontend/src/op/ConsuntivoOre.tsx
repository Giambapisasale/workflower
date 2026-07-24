/**
 * "Le mie ore": l'operaio segna le ore fatte, un passo alla volta —
 * giorno → cantiere → quante ore → cosa hai fatto → conferma. Nessun form,
 * bottoni grandi. Le ore vanno in ufficio per il controllo; la paga oraria
 * non si tocca qui, arriva dal profilo del dipendente.
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  api,
  type AttivitaScelta,
  type Cantiere,
  type ConsuntivoContesto,
} from "../shared/api";
import { TESTI, dataBreve } from "./testi";
import { Bottone, Card, Indietro, Titolo } from "./ui";

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

  return (
    <div>
      <Indietro a="/op" />
      <Titolo>{TESTI.titoloOre}</Titolo>

      {fase.tipo === "carica" || fase.tipo === "invio" ? (
        <Card>⏳ {TESTI.caricamento}</Card>
      ) : null}

      {fase.tipo === "nessuno" ? (
        <Card>
          <b>{TESTI.oreNessunDip}</b>
          <div className="mt-4">
            <Bottone icona="🏠" onClick={() => naviga("/op")}>
              {TESTI.tornaHome}
            </Bottone>
          </div>
        </Card>
      ) : null}

      {fase.tipo === "giorno" ? (
        <div className="space-y-4">
          <p className="text-[19px] font-bold">{TESTI.oreQuando}</p>
          <Bottone icona="📅" variante="primario" onClick={() => void scegliGiorno(oggi)}>
            {TESTI.oggi}
          </Bottone>
          <Bottone icona="📅" onClick={() => void scegliGiorno(ieri)}>
            {TESTI.ieri}
          </Bottone>
        </div>
      ) : null}

      {fase.tipo === "cantiere" ? (
        <div className="space-y-4">
          <p className="text-[19px] font-bold">{TESTI.oreQualeCantiere}</p>
          {(contesto?.cantieri ?? []).map((c) => (
            <Bottone
              key={c.id}
              icona="🏗️"
              onClick={() => {
                setCantiere(c);
                setFase({ tipo: "ore" });
              }}
            >
              {c.nome}
            </Bottone>
          ))}
        </div>
      ) : null}

      {fase.tipo === "ore" ? (
        <div className="space-y-5">
          <p className="text-[19px] font-bold">{TESTI.oreQuante}</p>
          <div className="flex items-center justify-between">
            <button
              type="button"
              className="min-h-[64px] w-20 rounded-2xl border-2 border-neutral-900 text-3xl font-bold disabled:opacity-30"
              onClick={() => setOre((o) => Math.max(ORE_MIN, o - ORE_PASSO))}
              disabled={ore <= ORE_MIN}
            >
              −
            </button>
            <div className="text-3xl font-bold">{TESTI.oreUnita(ore)}</div>
            <button
              type="button"
              className="min-h-[64px] w-20 rounded-2xl border-2 border-neutral-900 text-3xl font-bold disabled:opacity-30"
              onClick={() => setOre((o) => Math.min(ORE_MAX, o + ORE_PASSO))}
              disabled={ore >= ORE_MAX}
            >
              +
            </button>
          </div>
          <Bottone variante="primario" onClick={() => setFase({ tipo: "attivita" })}>
            {TESTI.oreAvanti}
          </Bottone>
        </div>
      ) : null}

      {fase.tipo === "attivita" ? (
        <div className="space-y-4">
          <p className="text-[19px] font-bold">{TESTI.oreCosaTitolo}</p>
          <p className="text-neutral-600">{TESTI.oreCosaSotto}</p>
          <div className="flex flex-wrap gap-2">
            {(contesto?.attivita_disponibili ?? []).map((a) => (
              <button
                key={a.id}
                type="button"
                onClick={() => alterna(a.id)}
                className={`min-h-[48px] rounded-2xl border-2 px-4 py-2 text-[17px] font-bold ${
                  scelte.has(a.id)
                    ? "border-green-700 bg-green-700 text-white"
                    : "border-neutral-300 bg-white text-neutral-900"
                }`}
              >
                {a.descrizione}
              </button>
            ))}
          </div>
          <input
            className="w-full rounded-2xl border-2 border-neutral-300 px-4 py-4 text-[18px] focus:border-neutral-900 focus:outline-none"
            value={nota}
            onChange={(e) => setNota(e.target.value)}
            placeholder={TESTI.oreAltro}
          />
          <Bottone variante="primario" onClick={() => setFase({ tipo: "conferma" })}>
            {scelte.size > 0 || nota.trim() ? TESTI.oreAvanti : TESTI.oreSalta}
          </Bottone>
        </div>
      ) : null}

      {fase.tipo === "conferma" ? (
        <div className="space-y-4">
          <p className="text-[19px] font-bold">{TESTI.oreConferma}</p>
          <Card>
            <div className="text-[18px]">
              🏗️ <b>{cantiere?.nome}</b>
            </div>
            <div className="mt-1 text-neutral-700">
              📅 {quando} · ⏱️ {TESTI.oreUnita(ore)}
            </div>
            {scelte.size > 0 || nota.trim() ? (
              <div className="mt-2 text-neutral-700">
                🔧{" "}
                {[
                  ...(contesto?.attivita_disponibili ?? [])
                    .filter((a) => scelte.has(a.id))
                    .map((a) => a.descrizione),
                  ...(nota.trim() ? [nota.trim()] : []),
                ].join(", ")}
              </div>
            ) : null}
          </Card>
          <Bottone variante="conferma" onClick={() => void invia()}>
            {TESTI.oreInvia}
          </Bottone>
        </div>
      ) : null}

      {fase.tipo === "inviato" ? (
        <Card>
          <b>{TESTI.oreInviato}</b>
          <p className="mt-1 text-neutral-600">{TESTI.oreInviatoSotto}</p>
          <div className="mt-4">
            <Bottone icona="🏠" onClick={() => naviga("/op")}>
              {TESTI.tornaHome}
            </Bottone>
          </div>
        </Card>
      ) : null}

      {fase.tipo === "avviso" ? (
        <Card>
          <b>{fase.messaggio}</b>
          <div className="mt-4 space-y-3">
            <Bottone variante="primario" onClick={() => setFase({ tipo: "giorno" })}>
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
