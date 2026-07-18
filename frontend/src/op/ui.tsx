/** Mattoni della UI operatore: bottoni giganti (touch ≥ 48px) e card. */

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";
import { TESTI } from "./testi";

type VarianteBottone = "primario" | "normale" | "conferma";

const STILE_BOTTONE: Record<VarianteBottone, string> = {
  primario: "border-neutral-900 bg-neutral-900 text-white active:bg-black",
  normale: "border-neutral-900 bg-white text-neutral-900 active:bg-neutral-100",
  conferma: "border-green-700 bg-green-700 text-white active:bg-green-800",
};

const BASE_BOTTONE =
  "flex w-full min-h-[64px] items-center gap-4 rounded-2xl border-2 px-5 py-4 " +
  "text-left text-[19px] font-bold disabled:opacity-40";

export function Bottone({
  icona,
  variante = "normale",
  children,
  ...resto
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  icona?: string;
  variante?: VarianteBottone;
}) {
  return (
    <button type="button" className={`${BASE_BOTTONE} ${STILE_BOTTONE[variante]}`} {...resto}>
      {icona ? <span className="text-3xl leading-none">{icona}</span> : null}
      <span>{children}</span>
    </button>
  );
}

export function BottoneLink({
  a,
  icona,
  variante = "normale",
  children,
}: {
  a: string;
  icona?: string;
  variante?: VarianteBottone;
  children: ReactNode;
}) {
  return (
    <Link to={a} className={`${BASE_BOTTONE} ${STILE_BOTTONE[variante]}`}>
      {icona ? <span className="text-3xl leading-none">{icona}</span> : null}
      <span>{children}</span>
    </Link>
  );
}

export function BottoneFile({
  icona,
  variante = "normale",
  accept,
  capture,
  onFile,
  children,
}: {
  icona?: string;
  variante?: VarianteBottone;
  accept: string;
  capture?: boolean | "user" | "environment";
  onFile: (file: File | null) => void;
  children: ReactNode;
}) {
  return (
    <label className={`${BASE_BOTTONE} ${STILE_BOTTONE[variante]} cursor-pointer`}>
      {icona ? <span className="text-3xl leading-none">{icona}</span> : null}
      <span>{children}</span>
      <input
        type="file"
        className="hidden"
        accept={accept}
        capture={capture}
        onChange={(e) => {
          onFile(e.target.files?.[0] ?? null);
          e.target.value = "";
        }}
      />
    </label>
  );
}

export function Card({ children }: { children: ReactNode }) {
  return (
    <div className="mb-3 rounded-2xl border-2 border-neutral-300 p-4">{children}</div>
  );
}

export function Indietro({ a }: { a: string }) {
  return (
    <Link to={a} className="mb-2 inline-block min-h-[48px] py-2 pr-4 text-neutral-500">
      {TESTI.indietro}
    </Link>
  );
}

export function Titolo({ children }: { children: ReactNode }) {
  return <h1 className="mb-4 text-[23px] font-bold">{children}</h1>;
}
