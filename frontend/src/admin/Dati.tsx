/** Hub della gestione manuale (M13): i tipi gestibili, per anagrafiche e documenti. */

import { Link } from "react-router-dom";
import { admin, type MetaTipo } from "./api";
import { useCarica } from "./formato";
import { Card, Errore, Stato } from "./ui";

function Riquadri({ tipi }: { tipi: MetaTipo[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
      {tipi.map((t) => (
        <Link
          key={t.tipo}
          to={`/admin/dati/${t.tipo}`}
          className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:border-sky-300 hover:shadow"
        >
          <div className="text-base font-semibold text-slate-800">{t.etichetta}</div>
          <div className="mt-1 text-xs text-slate-400">apri e gestisci →</div>
        </Link>
      ))}
    </div>
  );
}

export default function Dati() {
  const { dati, errore, inCorso } = useCarica(() => admin.entitiesMeta());
  if (inCorso) return <Stato>Carico…</Stato>;
  if (errore || !dati) return <Errore>{errore ?? "Nessun dato"}</Errore>;
  const master = dati.filter((t) => t.is_master);
  const documenti = dati.filter((t) => !t.is_master);

  return (
    <>
      <div className="mb-4">
        <h1 className="text-lg font-bold">Gestione dati</h1>
        <p className="text-sm text-slate-500">
          Inserisci, correggi o elimina i dati a mano. Ogni modifica resta tracciata.
        </p>
      </div>
      <Card titolo="Anagrafiche">
        <Riquadri tipi={master} />
      </Card>
      <Card titolo="Documenti gestionali">
        <Riquadri tipi={documenti} />
      </Card>
    </>
  );
}
