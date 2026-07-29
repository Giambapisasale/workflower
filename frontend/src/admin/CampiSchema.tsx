/**
 * Form generato dallo schema JSON dell'entità (M13). Nessun form scritto a mano
 * per tipo: i campi (testo, numero, data, riferimento con picker, righe/voci
 * ripetibili) nascono dallo schema. Si lega all'INTERO oggetto `dati`, così i
 * campi non mostrati (es. `voce_computo_id`) fanno round-trip senza perdersi.
 * L'autorità di validazione resta il backend (DAL): qui si guida solo l'input.
 */

import type { JsonSchema, VoceEntita } from "./api";
import { Input, Select } from "../ds";
import type { SelectItem } from "../ds";
import { Bottone, EtichettaCampo } from "./ui";

type Opzioni = Record<string, VoceEntita[]>; // tipo → voci per i picker
type Etichette = Record<string, string>; // tipo → etichetta

type Props = {
  schema: JsonSchema;
  valore: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
  riferimenti: Record<string, string>; // campo → tipo referenziato
  opzioni: Opzioni;
  etichette: Etichette;
};

const LARGO = { width: "100%" } as const;

function tipiDi(schema: JsonSchema): string[] {
  return Array.isArray(schema.type) ? schema.type : schema.type ? [schema.type] : [];
}

function nullable(schema: JsonSchema): boolean {
  return tipiDi(schema).includes("null");
}

function umana(chiave: string): string {
  const s = chiave.replace(/_id$/, "").replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function etichettaCampo(
  campo: string,
  riferimenti: Record<string, string>,
  etichette: Etichette,
): string {
  const tipoRif = riferimenti[campo];
  if (tipoRif) return etichette[tipoRif] ?? umana(campo);
  return umana(campo);
}

function valoreDefault(schema: JsonSchema): unknown {
  if (nullable(schema)) return null;
  const tipi = tipiDi(schema);
  if (tipi.includes("number") || tipi.includes("integer")) return 0;
  if (tipi.includes("array")) return [];
  if (tipi.includes("boolean")) return false;
  return "";
}

/** Un campo scalare (o riferimento) dello schema. */
function Campo({
  schema,
  valore,
  onChange,
  obbligatorio,
  etichetta,
  tipoRiferimento,
  opzioni,
}: {
  schema: JsonSchema;
  valore: unknown;
  onChange: (v: unknown) => void;
  obbligatorio: boolean;
  etichetta: string;
  tipoRiferimento?: string;
  opzioni: Opzioni;
}) {
  const tipi = tipiDi(schema);
  const puoEsserVuoto = !obbligatorio || nullable(schema);
  const intestazione = <EtichettaCampo obbligatorio={obbligatorio}>{etichetta}</EtichettaCampo>;

  /** Il picker del design system non ha la voce vuota: la si aggiunge in testa. */
  function scelta(voci: SelectItem[], vuoto: string) {
    return (
      <Select
        items={puoEsserVuoto ? [{ value: "", textValue: vuoto }, ...voci] : voci}
        placeholder={puoEsserVuoto ? vuoto : "— scegli —"}
        value={(valore as string) ?? ""}
        onValueChange={(v) => onChange(v || (puoEsserVuoto ? null : ""))}
        style={LARGO}
      />
    );
  }

  // Riferimento a un'altra entità → picker
  if (tipoRiferimento) {
    const voci = (opzioni[tipoRiferimento] ?? []).map((v) => ({
      value: v.id,
      textValue: v.titolo ?? v.id,
    }));
    return (
      <div>
        {intestazione}
        {scelta(voci, "— nessuno —")}
        {schema.description ? <Nota testo={schema.description} /> : null}
      </div>
    );
  }

  // enum → select
  if (schema.enum) {
    const voci = schema.enum.map((v) => ({ value: String(v), textValue: String(v) }));
    return (
      <div>
        {intestazione}
        {scelta(voci, "— nessuno —")}
      </div>
    );
  }

  // numero
  if (tipi.includes("number") || tipi.includes("integer")) {
    return (
      <div>
        {intestazione}
        <Input
          type="number"
          step="any"
          style={LARGO}
          value={valore === null || valore === undefined ? "" : String(valore)}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === "") return onChange(puoEsserVuoto ? null : "");
            const n = Number(raw);
            onChange(Number.isNaN(n) ? raw : n);
          }}
        />
        {schema.description ? <Nota testo={schema.description} /> : null}
      </div>
    );
  }

  // data
  if (schema.format === "date") {
    return (
      <div>
        {intestazione}
        <Input
          type="date"
          style={LARGO}
          value={(valore as string) ?? ""}
          onChange={(e) => onChange(e.target.value || (puoEsserVuoto ? null : ""))}
        />
      </div>
    );
  }

  // testo (default)
  return (
    <div>
      {intestazione}
      <Input
        type="text"
        style={LARGO}
        value={(valore as string) ?? ""}
        onChange={(e) => onChange(e.target.value === "" && puoEsserVuoto ? null : e.target.value)}
      />
      {schema.description ? <Nota testo={schema.description} /> : null}
    </div>
  );
}

function Nota({ testo }: { testo: string }) {
  return (
    <p style={{ margin: "6px 0 0", fontSize: 12, color: "var(--text-secondary)" }}>{testo}</p>
  );
}

/** Un array di oggetti (righe di fattura/DDT, voci di computo): sotto-form ripetibili. */
function CampoArray({
  schema,
  valore,
  onChange,
  etichetta,
  riferimenti,
  opzioni,
  etichette,
}: {
  schema: JsonSchema;
  valore: unknown[];
  onChange: (v: unknown[]) => void;
  etichetta: string;
  riferimenti: Record<string, string>;
  opzioni: Opzioni;
  etichette: Etichette;
}) {
  const item = schema.items ?? {};
  const props = item.properties ?? {};
  const richiesti = new Set(item.required ?? []);
  const righe = Array.isArray(valore) ? valore : [];

  const nuovaRiga = () => {
    const riga: Record<string, unknown> = {};
    for (const [k, s] of Object.entries(props)) riga[k] = valoreDefault(s);
    onChange([...righe, riga]);
  };
  const aggiorna = (i: number, riga: Record<string, unknown>) =>
    onChange(righe.map((r, j) => (j === i ? riga : r)));
  const rimuovi = (i: number) => onChange(righe.filter((_, j) => j !== i));

  return (
    <div
      style={{
        gridColumn: "1 / -1",
        border: "1px solid var(--border-color)",
        borderRadius: "var(--radius)",
        background: "var(--background-secondary)",
        padding: 16,
      }}
    >
      <div
        style={{
          marginBottom: 12,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <EtichettaCampo>
          {etichetta} ({righe.length})
        </EtichettaCampo>
        <Bottone onClick={nuovaRiga}>+ Aggiungi</Bottone>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {righe.map((riga, i) => (
          <div
            key={i}
            style={{
              border: "1px solid var(--border-color)",
              borderRadius: "var(--radius)",
              background: "var(--background-primary)",
              padding: 16,
            }}
          >
            <div
              style={{
                marginBottom: 12,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>#{i + 1}</span>
              <Bottone variante="pericolo" onClick={() => rimuovi(i)}>
                Rimuovi
              </Bottone>
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                gap: 16,
              }}
            >
              {Object.entries(props).map(([k, s]) => (
                <Campo
                  key={k}
                  schema={s}
                  valore={(riga as Record<string, unknown>)[k]}
                  onChange={(v) => aggiorna(i, { ...(riga as Record<string, unknown>), [k]: v })}
                  obbligatorio={richiesti.has(k)}
                  etichetta={etichettaCampo(k, riferimenti, etichette)}
                  tipoRiferimento={riferimenti[k]}
                  opzioni={opzioni}
                />
              ))}
            </div>
          </div>
        ))}
        {righe.length === 0 ? (
          <p style={{ margin: 0, fontSize: 14, color: "var(--text-secondary)" }}>
            Nessuna riga. Usa “+ Aggiungi”.
          </p>
        ) : null}
      </div>
    </div>
  );
}

export default function CampiSchema({
  schema,
  valore,
  onChange,
  riferimenti,
  opzioni,
  etichette,
}: Props) {
  const props = schema.properties ?? {};
  const richiesti = new Set(schema.required ?? []);
  const imposta = (campo: string, v: unknown) => onChange({ ...valore, [campo]: v });

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
        gap: 20,
      }}
    >
      {Object.entries(props).map(([campo, sotto]) => {
        const isArray = tipiDi(sotto).includes("array");
        // Oggetti freeform (es. `riferimenti_estratti`) non hanno un editor: si
        // saltano, ma il valore fa comunque round-trip (`imposta` fa spread di
        // `...valore`), così non si perde al salvataggio.
        if (!isArray && tipiDi(sotto).includes("object") && !riferimenti[campo]) return null;
        const etichetta = etichettaCampo(campo, riferimenti, etichette);
        if (isArray && (sotto.items?.properties ?? null)) {
          return (
            <CampoArray
              key={campo}
              schema={sotto}
              valore={(valore[campo] as unknown[]) ?? []}
              onChange={(v) => imposta(campo, v)}
              etichetta={etichetta}
              riferimenti={riferimenti}
              opzioni={opzioni}
              etichette={etichette}
            />
          );
        }
        return (
          <Campo
            key={campo}
            schema={sotto}
            valore={valore[campo]}
            onChange={(v) => imposta(campo, v)}
            obbligatorio={richiesti.has(campo)}
            etichetta={etichetta}
            tipoRiferimento={riferimenti[campo]}
            opzioni={opzioni}
          />
        );
      })}
    </div>
  );
}
