-- Catalogo viste DuckDB sul repo dati (sola lettura).
-- ${DATA_DIR} è sostituito a runtime da app/core/views.py con il percorso assoluto.
-- Colonne esplicite: le viste sono il contratto stabile per query e cruscotti,
-- i campi JSON non elencati vengono ignorati.
-- Convenzione: niente punto e virgola nei literal, niente commenti in coda alle righe.

CREATE OR REPLACE VIEW v_cantieri AS
SELECT id,
       stato,
       dati.nome               AS nome,
       dati.indirizzo          AS indirizzo,
       dati.comune             AS comune,
       dati.provincia          AS provincia,
       dati.committente        AS committente,
       dati.budget             AS budget,
       dati.data_inizio        AS data_inizio,
       dati.data_fine_prevista AS data_fine_prevista,
       dati.capocantiere       AS capocantiere
FROM read_json(
    '${DATA_DIR}/entities/cantieri/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            nome VARCHAR, indirizzo VARCHAR, comune VARCHAR, provincia VARCHAR,
            committente VARCHAR, budget DOUBLE, data_inizio DATE,
            data_fine_prevista DATE, capocantiere VARCHAR
        )'
    }
);

CREATE OR REPLACE VIEW v_fornitori AS
SELECT id,
       stato,
       dati.ragione_sociale AS ragione_sociale,
       dati.partita_iva     AS partita_iva,
       dati.categoria       AS categoria,
       dati.comune          AS comune,
       dati.pec             AS pec,
       dati.telefono        AS telefono
FROM read_json(
    '${DATA_DIR}/entities/fornitori/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            ragione_sociale VARCHAR, partita_iva VARCHAR, categoria VARCHAR,
            comune VARCHAR, pec VARCHAR, telefono VARCHAR
        )'
    }
);

CREATE OR REPLACE VIEW v_fatture AS
SELECT id,
       stato,
       dati.numero           AS numero,
       dati.data             AS data,
       dati.fornitore_id     AS fornitore_id,
       dati.cantiere_id      AS cantiere_id,
       dati.imponibile       AS imponibile,
       dati.iva              AS iva,
       dati.totale           AS totale,
       dati.ritenuta_acconto AS ritenuta_acconto,
       len(dati.righe)       AS n_righe,
       meta.workflow         AS workflow,
       meta.validato_da      AS validato_da
FROM read_json(
    '${DATA_DIR}/entities/fatture/*/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            numero VARCHAR, data DATE, fornitore_id VARCHAR, cantiere_id VARCHAR,
            imponibile DOUBLE, iva DOUBLE, totale DOUBLE, ritenuta_acconto DOUBLE,
            righe STRUCT(
                descrizione VARCHAR, quantita DOUBLE, unita_misura VARCHAR,
                importo DOUBLE, voce_computo_id VARCHAR
            )[]
        )',
        meta: 'STRUCT(workflow VARCHAR, validato_da VARCHAR)'
    }
);

CREATE OR REPLACE VIEW v_fatture_righe AS
SELECT id                AS fattura_id,
       dati.cantiere_id  AS cantiere_id,
       dati.fornitore_id AS fornitore_id,
       dati.numero       AS numero,
       dati.data         AS data,
       unnest(dati.righe, recursive := true)
FROM read_json(
    '${DATA_DIR}/entities/fatture/*/*.json',
    columns = {
        id: 'VARCHAR',
        dati: 'STRUCT(
            numero VARCHAR, data DATE, fornitore_id VARCHAR, cantiere_id VARCHAR,
            righe STRUCT(
                descrizione VARCHAR, quantita DOUBLE, unita_misura VARCHAR,
                importo DOUBLE, voce_computo_id VARCHAR
            )[]
        )'
    }
);

CREATE OR REPLACE VIEW v_ddt AS
SELECT id,
       stato,
       dati.numero             AS numero,
       dati.data               AS data,
       dati.fornitore_id       AS fornitore_id,
       dati.cantiere_id        AS cantiere_id,
       dati.causale            AS causale,
       dati.riferimento_ordine AS riferimento_ordine,
       len(dati.righe)         AS n_righe,
       meta.workflow           AS workflow,
       meta.validato_da        AS validato_da
FROM read_json(
    '${DATA_DIR}/entities/ddt/*/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            numero VARCHAR, data DATE, fornitore_id VARCHAR, cantiere_id VARCHAR,
            causale VARCHAR, riferimento_ordine VARCHAR,
            righe STRUCT(
                descrizione VARCHAR, quantita DOUBLE, unita_misura VARCHAR,
                voce_computo_id VARCHAR
            )[]
        )',
        meta: 'STRUCT(workflow VARCHAR, validato_da VARCHAR)'
    }
);

CREATE OR REPLACE VIEW v_ddt_righe AS
SELECT id                AS ddt_id,
       dati.cantiere_id  AS cantiere_id,
       dati.fornitore_id AS fornitore_id,
       dati.numero       AS numero,
       dati.data         AS data,
       unnest(dati.righe, recursive := true)
FROM read_json(
    '${DATA_DIR}/entities/ddt/*/*.json',
    columns = {
        id: 'VARCHAR',
        dati: 'STRUCT(
            numero VARCHAR, data DATE, fornitore_id VARCHAR, cantiere_id VARCHAR,
            righe STRUCT(
                descrizione VARCHAR, quantita DOUBLE, unita_misura VARCHAR,
                voce_computo_id VARCHAR
            )[]
        )'
    }
);

CREATE OR REPLACE VIEW v_sal AS
SELECT id,
       stato,
       dati.numero                  AS numero,
       dati.data                    AS data,
       dati.cantiere_id             AS cantiere_id,
       dati.importo_lavori          AS importo_lavori,
       dati.importo_progressivo     AS importo_progressivo,
       dati.percentuale_avanzamento AS percentuale_avanzamento,
       meta.workflow                AS workflow,
       meta.validato_da             AS validato_da
FROM read_json(
    '${DATA_DIR}/entities/sal/*/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            numero VARCHAR, data DATE, cantiere_id VARCHAR, importo_lavori DOUBLE,
            importo_progressivo DOUBLE, percentuale_avanzamento DOUBLE
        )',
        meta: 'STRUCT(workflow VARCHAR, validato_da VARCHAR)'
    }
);

CREATE OR REPLACE VIEW v_rapportini AS
SELECT id,
       stato,
       dati.data                                        AS data,
       dati.cantiere_id                                 AS cantiere_id,
       len(dati.righe)                                  AS n_righe,
       list_sum(list_transform(dati.righe, r -> r.ore)) AS ore_totali,
       meta.workflow                                    AS workflow,
       meta.validato_da                                 AS validato_da
FROM read_json(
    '${DATA_DIR}/entities/rapportini/*/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            data DATE, cantiere_id VARCHAR,
            righe STRUCT(
                nominativo VARCHAR, mansione VARCHAR, ore DOUBLE, costo_orario DOUBLE
            )[]
        )',
        meta: 'STRUCT(workflow VARCHAR, validato_da VARCHAR)'
    }
);

CREATE OR REPLACE VIEW v_rapportini_righe AS
SELECT rapportino_id,
       cantiere_id,
       data,
       nominativo,
       mansione,
       ore,
       costo_orario,
       ore * COALESCE(costo_orario, 0) AS costo
FROM (
    SELECT id               AS rapportino_id,
           dati.cantiere_id AS cantiere_id,
           dati.data        AS data,
           unnest(dati.righe, recursive := true)
    FROM read_json(
        '${DATA_DIR}/entities/rapportini/*/*.json',
        columns = {
            id: 'VARCHAR',
            dati: 'STRUCT(
                data DATE, cantiere_id VARCHAR,
                righe STRUCT(
                    nominativo VARCHAR, mansione VARCHAR, ore DOUBLE, costo_orario DOUBLE
                )[]
            )'
        }
    )
);

CREATE OR REPLACE VIEW v_materiali AS
SELECT id,
       stato,
       dati.codice          AS codice,
       dati.descrizione     AS descrizione,
       dati.unita_misura    AS unita_misura,
       dati.prezzo_unitario AS prezzo_unitario,
       dati.categoria       AS categoria,
       dati.fornitore_id    AS fornitore_id
FROM read_json(
    '${DATA_DIR}/entities/materiali/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            codice VARCHAR, descrizione VARCHAR, unita_misura VARCHAR,
            prezzo_unitario DOUBLE, categoria VARCHAR, fornitore_id VARCHAR
        )'
    }
);

CREATE OR REPLACE VIEW v_mezzi AS
SELECT id,
       stato,
       dati.targa        AS targa,
       dati.tipo         AS tipo,
       dati.descrizione  AS descrizione,
       dati.costo_orario AS costo_orario,
       dati.proprieta    AS proprieta
FROM read_json(
    '${DATA_DIR}/entities/mezzi/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            targa VARCHAR, tipo VARCHAR, descrizione VARCHAR,
            costo_orario DOUBLE, proprieta VARCHAR
        )'
    }
);

CREATE OR REPLACE VIEW v_lavorazioni AS
SELECT id,
       stato,
       dati.codice       AS codice,
       dati.descrizione  AS descrizione,
       dati.unita_misura AS unita_misura,
       dati.categoria    AS categoria
FROM read_json(
    '${DATA_DIR}/entities/lavorazioni/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            codice VARCHAR, descrizione VARCHAR, unita_misura VARCHAR, categoria VARCHAR
        )'
    }
);

CREATE OR REPLACE VIEW v_scadenze AS
SELECT id,
       stato,
       dati.descrizione   AS descrizione,
       dati.data_scadenza AS data_scadenza,
       dati.tipo          AS tipo,
       dati.cantiere_id   AS cantiere_id,
       dati.stato         AS stato_adempimento
FROM read_json(
    '${DATA_DIR}/entities/scadenze/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            descrizione VARCHAR, data_scadenza DATE, tipo VARCHAR,
            cantiere_id VARCHAR, stato VARCHAR
        )'
    }
);

CREATE OR REPLACE VIEW v_computo AS
SELECT id,
       stato,
       dati.cantiere_id AS cantiere_id,
       dati.descrizione AS descrizione,
       len(dati.voci)   AS n_voci,
       list_sum(list_transform(dati.voci, v -> v.importo)) AS importo_previsto,
       meta.validato_da AS validato_da
FROM read_json(
    '${DATA_DIR}/entities/computi/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            cantiere_id VARCHAR, descrizione VARCHAR,
            voci STRUCT(
                id VARCHAR, codice VARCHAR, descrizione VARCHAR, unita_misura VARCHAR,
                quantita DOUBLE, prezzo_unitario DOUBLE, importo DOUBLE, categoria VARCHAR
            )[]
        )',
        meta: 'STRUCT(validato_da VARCHAR)'
    }
);

CREATE OR REPLACE VIEW v_computo_voci AS
SELECT computo_id,
       cantiere_id,
       id           AS voce_id,
       codice,
       descrizione,
       unita_misura,
       quantita,
       prezzo_unitario,
       importo      AS previsto,
       categoria
FROM (
    SELECT id               AS computo_id,
           dati.cantiere_id AS cantiere_id,
           unnest(dati.voci, recursive := true)
    FROM read_json(
        '${DATA_DIR}/entities/computi/*.json',
        columns = {
            id: 'VARCHAR',
            dati: 'STRUCT(
                cantiere_id VARCHAR,
                voci STRUCT(
                    id VARCHAR, codice VARCHAR, descrizione VARCHAR, unita_misura VARCHAR,
                    quantita DOUBLE, prezzo_unitario DOUBLE, importo DOUBLE, categoria VARCHAR
                )[]
            )'
        }
    )
);

CREATE OR REPLACE VIEW v_scostamento_voci AS
SELECT vc.cantiere_id            AS cantiere_id,
       vc.voce_id                AS voce_id,
       vc.codice                 AS codice,
       vc.descrizione            AS descrizione,
       vc.categoria              AS categoria,
       vc.previsto               AS previsto,
       COALESCE(sp.consuntivo, 0) AS consuntivo,
       COALESCE(sp.consuntivo, 0) - vc.previsto AS delta,
       CASE WHEN vc.previsto > 0 THEN COALESCE(sp.consuntivo, 0) / vc.previsto END AS quota
FROM v_computo_voci vc
LEFT JOIN (
    SELECT cantiere_id, voce_computo_id, SUM(importo) AS consuntivo
    FROM v_fatture_righe
    WHERE voce_computo_id IS NOT NULL
    GROUP BY cantiere_id, voce_computo_id
) sp ON sp.cantiere_id = vc.cantiere_id AND sp.voce_computo_id = vc.voce_id;

CREATE OR REPLACE VIEW v_cantiere_scostamento AS
SELECT cantiere_id,
       SUM(previsto)                 AS previsto,
       SUM(consuntivo)               AS consuntivo_abbinato,
       SUM(consuntivo) - SUM(previsto) AS delta
FROM v_scostamento_voci
GROUP BY cantiere_id;
