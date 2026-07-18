/** Mattoni della console Admin: componenti di layout (formattazioni in formato.ts). */

import type { ReactNode } from "react";

export function Card({
  titolo,
  azioni,
  children,
}: {
  titolo?: ReactNode;
  azioni?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="mb-6 rounded-xl border border-slate-200 bg-white shadow-sm">
      {(titolo || azioni) && (
        <header className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{titolo}</h2>
          {azioni}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Kpi({
  etichetta,
  valore,
  nota,
}: {
  etichetta: string;
  valore: ReactNode;
  nota?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-400">{etichetta}</div>
      <div className="mt-1 text-2xl font-bold text-slate-800">{valore}</div>
      {nota ? <div className="mt-1 text-xs text-slate-500">{nota}</div> : null}
    </div>
  );
}

const TONI: Record<string, string> = {
  verde: "bg-green-100 text-green-800",
  giallo: "bg-amber-100 text-amber-800",
  rosso: "bg-red-100 text-red-800",
  blu: "bg-sky-100 text-sky-800",
  grigio: "bg-slate-100 text-slate-600",
};

export function Badge({ tono = "grigio", children }: { tono?: string; children: ReactNode }) {
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${TONI[tono]}`}>
      {children}
    </span>
  );
}

export function Bottone({
  variante = "normale",
  children,
  ...resto
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variante?: "primario" | "normale" | "pericolo" }) {
  const stili = {
    primario: "bg-slate-800 text-white hover:bg-slate-900",
    normale: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
    pericolo: "border border-red-300 bg-white text-red-700 hover:bg-red-50",
  }[variante];
  return (
    <button
      type="button"
      className={`rounded-lg px-3.5 py-2 text-sm font-medium disabled:opacity-40 ${stili}`}
      {...resto}
    >
      {children}
    </button>
  );
}

export function Stato({ children }: { children: ReactNode }) {
  return <div className="py-10 text-center text-slate-400">{children}</div>;
}

export function Errore({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
      {children}
    </div>
  );
}
