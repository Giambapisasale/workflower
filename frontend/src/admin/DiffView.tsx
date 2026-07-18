/** Diff unificato colorato (verde = aggiunte, rosso = rimozioni). */

function colore(riga: string): string {
  if (riga.startsWith("+++") || riga.startsWith("---")) return "text-slate-500";
  if (riga.startsWith("+")) return "text-green-400";
  if (riga.startsWith("-")) return "text-red-400";
  if (riga.startsWith("@@")) return "text-sky-400";
  return "text-slate-300";
}

export default function DiffView({ diff }: { diff: string }) {
  if (!diff.trim()) return <div className="text-sm text-slate-400">Nessuna modifica al testo.</div>;
  return (
    <pre className="overflow-auto rounded-lg bg-slate-900 p-3 font-mono text-xs leading-5">
      {diff.split("\n").map((riga, i) => (
        <div key={i} className={colore(riga)}>{riga || " "}</div>
      ))}
    </pre>
  );
}
