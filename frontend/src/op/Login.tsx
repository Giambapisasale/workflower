/** Accesso "a prova di cantiere": una domanda alla volta, niente form complessi. */

import { useState } from "react";
import { api, type Sessione } from "../shared/api";
import { Input } from "../ds";
import { TESTI } from "./testi";
import { Avviso, BottonePieno, Indietro } from "./ui";

const STILE_CAMPO = { width: "100%", fontSize: 18, padding: "12px 14px" } as const;

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
        <div
          style={{
            fontSize: 13,
            letterSpacing: ".12em",
            textTransform: "uppercase",
            color: "var(--text-secondary)",
            marginBottom: 28,
          }}
        >
          {TESTI.marchio}
        </div>
        <h1 style={{ fontSize: 23, fontWeight: 700, margin: "0 0 20px" }}>{TESTI.chiSei}</h1>
        <div style={{ marginBottom: 20 }}>
          <Input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder={TESTI.segnapostoNome}
            style={STILE_CAMPO}
            autoCapitalize="none"
            autoCorrect="off"
            autoFocus
          />
        </div>
        <BottonePieno tipo="submit" disabled={!nome.trim()}>
          {TESTI.avanti}
        </BottonePieno>
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
      <Indietro
        onClick={() => {
          setPasso("nome");
          setAvviso(null);
        }}
      />
      <h1 style={{ fontSize: 23, fontWeight: 700, margin: "12px 0 20px" }}>
        {TESTI.ilTuoCodice(nome.trim())}
      </h1>
      <div style={{ marginBottom: 20 }}>
        <Input
          type="password"
          value={codice}
          onChange={(e) => setCodice(e.target.value)}
          placeholder={TESTI.segnapostoCodice}
          style={STILE_CAMPO}
          inputMode="numeric"
          autoFocus
        />
      </div>
      {avviso ? <Avviso>{avviso}</Avviso> : null}
      <BottonePieno tipo="submit" disabled={!codice.trim() || attesa}>
        {attesa ? TESTI.caricamento : TESTI.entra}
      </BottonePieno>
    </form>
  );
}
