/** Formattazioni e un piccolo hook di caricamento dati, condivisi dalle pagine Admin. */

import { useCallback, useEffect, useState } from "react";
import { ErroreApi } from "../shared/api";

export function euro(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(v);
}

export function percento(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat("it-IT", { style: "percent", maximumFractionDigits: 1 }).format(v);
}

export function dataBreve(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleDateString("it-IT");
}

type StatoCarica<T> = {
  dati: T | null;
  errore: string | null;
  inCorso: boolean;
  ricarica: () => void;
};

/** Carica dati async con stato di errore/caricamento e una `ricarica` manuale. */
export function useCarica<T>(fn: () => Promise<T>, deps: unknown[] = []): StatoCarica<T> {
  const [dati, setDati] = useState<T | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [inCorso, setInCorso] = useState(true);
  const [tick, setTick] = useState(0);
  const ricarica = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let vivo = true;
    setInCorso(true);
    setErrore(null);
    fn()
      .then((r) => vivo && setDati(r))
      .catch((e) => vivo && setErrore(e instanceof ErroreApi ? e.message : "Errore di rete"))
      .finally(() => vivo && setInCorso(false));
    return () => {
      vivo = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { dati, errore, inCorso, ricarica };
}
