/** Hub della gestione manuale (M13): i tipi gestibili, per anagrafiche e documenti. */

import { admin, type MetaTipo } from "./api";
import { useCarica } from "./formato";
import { Badge, Card, Errore, IntestazionePagina, Riquadro, Stato } from "./ui";

function Riquadri({ tipi }: { tipi: MetaTipo[] }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
        gap: 12,
      }}
    >
      {tipi.map((t) => (
        <Riquadro
          key={t.tipo}
          a={`/admin/dati/${t.tipo}`}
          titolo={t.etichetta}
          sotto="apri e gestisci →"
        />
      ))}
    </div>
  );
}

export default function Dati() {
  const { dati, errore, inCorso } = useCarica(() => admin.entitiesMeta());
  const scartati = useCarica(() => admin.scartati());
  if (inCorso) return <Stato>Carico…</Stato>;
  if (errore || !dati) return <Errore>{errore ?? "Nessun dato"}</Errore>;
  const master = dati.filter((t) => t.is_master);
  const documenti = dati.filter((t) => !t.is_master);
  const quantiScartati = scartati.dati?.length ?? 0;

  return (
    <>
      <IntestazionePagina
        titolo="Gestione dati"
        sotto="Inserisci, correggi o elimina i dati a mano. Ogni modifica resta tracciata."
      />
      <Card titolo="Anagrafiche">
        <Riquadri tipi={master} />
      </Card>
      <Card titolo="Documenti gestionali">
        <Riquadri tipi={documenti} />
      </Card>
      <Card titolo="Scartati">
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 16 }}>
          <Riquadro
            a="/admin/dati/scartati"
            titolo="Inserimenti scartati"
            badge={quantiScartati > 0 ? <Badge tono="giallo">{quantiScartati}</Badge> : undefined}
            sotto="apri e ripristina →"
          />
          <p
            style={{
              maxWidth: "28rem",
              margin: 0,
              fontSize: 14,
              color: "var(--text-secondary)",
              textWrap: "pretty",
            }}
          >
            I documenti che l'ufficio ha ripudiato. Non contano nei costi e non sono cancellati:
            da lì si ripristinano.
          </p>
        </div>
      </Card>
    </>
  );
}
