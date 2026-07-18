/** Accesso "a prova di cantiere": una domanda alla volta, niente form complessi. */

import { useState } from "react";
import { api, type Sessione } from "../shared/api";
import { TESTI } from "./testi";
import { Bottone, Titolo } from "./ui";

const STILE_CAMPO =
  "mb-4 w-full rounded-2xl border-2 border-neutral-300 px-4 py-4 text-[19px] " +
  "focus:border-neutral-900 focus:outline-none";

export default function Login({ onEntra }: { onEntra: (sessione: Sessione) => void }) {
  const [passo, setPasso] = useState<"nome" | "codice">("nome");
  const [nome, setNome] = useState("");
  const [codice, setCodice] = useState("");
  const [avviso, setAvviso] = useState<string | null>(null);
  const [attesa, setAttesa] = useState(false);

  async function entra() {
    if (attesa) return;
    setAttesa(true);
    setAvviso(null);
    try {
      onEntra(await api.login(nome.trim(), codice.trim()));
    } catch {
      setAvviso(TESTI.loginSbagliato);
      setCodice("");
    } finally {
      setAttesa(false);
    }
  }

  if (passo === "nome") {
    return (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (nome.trim()) setPasso("codice");
        }}
      >
        <div className="mb-4 text-5xl">👷</div>
        <Titolo>{TESTI.chiSei}</Titolo>
        <input
          className={STILE_CAMPO}
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          placeholder={TESTI.segnapostoNome}
          autoCapitalize="none"
          autoCorrect="off"
          autoFocus
        />
        <Bottone variante="primario" disabled={!nome.trim()} onClick={() => setPasso("codice")}>
          {TESTI.avanti}
        </Bottone>
      </form>
    );
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (codice.trim()) void entra();
      }}
    >
      <button
        type="button"
        className="mb-2 min-h-[48px] py-2 pr-4 text-neutral-500"
        onClick={() => setPasso("nome")}
      >
        {TESTI.indietro}
      </button>
      <Titolo>{TESTI.ilTuoCodice(nome.trim())}</Titolo>
      <input
        className={STILE_CAMPO}
        value={codice}
        onChange={(e) => setCodice(e.target.value)}
        placeholder={TESTI.segnapostoCodice}
        type="password"
        inputMode="numeric"
        autoFocus
      />
      {avviso ? <p className="mb-3 font-bold text-red-700">{avviso}</p> : null}
      <Bottone variante="primario" disabled={!codice.trim() || attesa} onClick={() => void entra()}>
        {attesa ? TESTI.caricamento : TESTI.entra}
      </Bottone>
    </form>
  );
}
