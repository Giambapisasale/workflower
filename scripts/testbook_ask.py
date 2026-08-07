"""Compatibilità per il vecchio nome dell'harness storico.

La raccolta delle interrogazioni storiche non chiama più l'applicazione. Per il
confronto offline usare preferibilmente ``testbook_legacy_sql.py``.
"""

from testbook_legacy_sql import main


if __name__ == "__main__":
    raise SystemExit(main())
