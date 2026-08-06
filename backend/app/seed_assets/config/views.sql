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
       dati.scadenza_pagamento AS scadenza_pagamento,
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
            scadenza_pagamento DATE,
            righe STRUCT(
                descrizione VARCHAR, quantita DOUBLE, unita_misura VARCHAR,
                importo DOUBLE, voce_computo_id VARCHAR, mezzo_id VARCHAR, tipo_costo VARCHAR
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
                importo DOUBLE, voce_computo_id VARCHAR, mezzo_id VARCHAR, tipo_costo VARCHAR
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

CREATE OR REPLACE VIEW v_dipendenti AS
SELECT id,
       stato,
       dati.nome           AS nome,
       dati.cognome        AS cognome,
       dati.tipo           AS tipo,
       dati.tariffa_oraria AS tariffa_oraria,
       dati.username       AS username
FROM read_json(
    '${DATA_DIR}/entities/dipendenti/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            nome VARCHAR, cognome VARCHAR, tipo VARCHAR,
            tariffa_oraria DOUBLE, username VARCHAR
        )'
    }
);

CREATE OR REPLACE VIEW v_allocazioni AS
SELECT dipendente_id,
       cantiere_id,
       da,
       a
FROM (
    SELECT id AS dipendente_id,
           unnest(dati.allocazioni, recursive := true)
    FROM read_json(
        '${DATA_DIR}/entities/dipendenti/*.json',
        columns = {
            id: 'VARCHAR',
            dati: 'STRUCT(allocazioni STRUCT(cantiere_id VARCHAR, da DATE, a DATE)[])'
        }
    )
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

-- Il costo orario arriva dal profilo del dipendente collegato (dipendente_id);
-- in mancanza si usa il costo_orario scritto sul documento (rapportini di terzi),
-- infine 0. Così la tariffa vive nell'anagrafica, non nel singolo rapportino.
CREATE OR REPLACE VIEW v_rapportini_righe AS
SELECT r.rapportino_id,
       r.cantiere_id,
       r.data,
       r.nominativo,
       r.dipendente_id,
       COALESCE(d.nome || ' ' || d.cognome, r.nominativo)   AS lavoratore,
       r.mansione,
       r.ore,
       r.costo_orario,
       COALESCE(d.tariffa_oraria, r.costo_orario, 0)        AS tariffa_applicata,
       r.ore * COALESCE(d.tariffa_oraria, r.costo_orario, 0) AS costo
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
                    nominativo VARCHAR, dipendente_id VARCHAR, mansione VARCHAR,
                    ore DOUBLE, costo_orario DOUBLE
                )[]
            )'
        }
    )
) r
LEFT JOIN v_dipendenti d ON r.dipendente_id = d.id;

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
       dati.descrizione           AS descrizione,
       dati.tipo                  AS tipo,
       dati.targa                 AS targa,
       dati.matricola             AS matricola,
       dati.anno                  AS anno,
       dati.proprieta             AS proprieta,
       dati.costo_orario          AS costo_orario,
       dati.fornitore_noleggio_id AS fornitore_noleggio_id,
       dati.canone                AS canone,
       dati.unita_canone          AS unita_canone,
       dati.valore_acquisto       AS valore_acquisto,
       dati.vita_utile_anni       AS vita_utile_anni,
       dati.costi_fissi_annui     AS costi_fissi_annui,
       dati.ore_annue_stimate     AS ore_annue_stimate
FROM read_json(
    '${DATA_DIR}/entities/mezzi/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            descrizione VARCHAR, tipo VARCHAR, targa VARCHAR, matricola VARCHAR,
            anno BIGINT, proprieta VARCHAR, costo_orario DOUBLE,
            fornitore_noleggio_id VARCHAR, canone DOUBLE, unita_canone VARCHAR,
            valore_acquisto DOUBLE, vita_utile_anni DOUBLE,
            costi_fissi_annui DOUBLE, ore_annue_stimate DOUBLE
        )'
    }
);

CREATE OR REPLACE VIEW v_manutenzioni AS
SELECT id,
       stato,
       dati.mezzo_id     AS mezzo_id,
       dati.data         AS data,
       dati.tipo         AS tipo,
       dati.descrizione  AS descrizione,
       dati.costo        AS costo,
       dati.fornitore_id AS fornitore_id,
       dati.contaore     AS contaore
FROM read_json(
    '${DATA_DIR}/entities/manutenzioni/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            mezzo_id VARCHAR, data DATE, tipo VARCHAR, descrizione VARCHAR,
            costo DOUBLE, fornitore_id VARCHAR, contaore DOUBLE
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
       dati.mezzo_id      AS mezzo_id,
       dati.stato         AS stato_adempimento
FROM read_json(
    '${DATA_DIR}/entities/scadenze/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            descrizione VARCHAR, data_scadenza DATE, tipo VARCHAR,
            cantiere_id VARCHAR, mezzo_id VARCHAR, stato VARCHAR
        )'
    }
);

CREATE OR REPLACE VIEW v_pozzetti AS
SELECT id,
       stato,
       dati.cantiere_id        AS cantiere_id,
       dati.codice             AS codice,
       dati.tipo               AS tipo,
       dati.ubicazione         AS ubicazione,
       dati.stato              AS stato_manufatto,
       dati.data_installazione AS data_installazione,
       dati.note               AS note
FROM read_json(
    '${DATA_DIR}/entities/pozzetti/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(
            cantiere_id VARCHAR, codice VARCHAR, tipo VARCHAR, ubicazione VARCHAR,
            stato VARCHAR, data_installazione DATE, note VARCHAR
        )'
    }
);

CREATE OR REPLACE VIEW v_pozzetti_riepilogo AS
SELECT cantiere_id,
       count(*)                                                      AS totale,
       count(*) FILTER (WHERE stato_manufatto = 'previsto')          AS previsti,
       count(*) FILTER (WHERE stato_manufatto = 'installato')        AS installati,
       count(*) FILTER (WHERE stato_manufatto = 'collaudato')        AS collaudati
FROM v_pozzetti
GROUP BY cantiere_id;

CREATE OR REPLACE VIEW v_cronoprogramma_voci AS
SELECT cronoprogramma_id,
       cantiere_id,
       lavorazione_id,
       descrizione,
       inizio_previsto,
       fine_prevista
FROM (
    SELECT id               AS cronoprogramma_id,
           dati.cantiere_id AS cantiere_id,
           unnest(dati.voci, recursive := true)
    FROM read_json(
        '${DATA_DIR}/entities/cronoprogrammi/*.json',
        columns = {
            id: 'VARCHAR',
            dati: 'STRUCT(
                cantiere_id VARCHAR,
                voci STRUCT(
                    lavorazione_id VARCHAR, descrizione VARCHAR,
                    inizio_previsto DATE, fine_prevista DATE
                )[]
            )'
        }
    )
);

CREATE OR REPLACE VIEW v_cronoprogramma AS
SELECT piano.cantiere_id                                    AS cantiere_id,
       piano.voci_totali                                    AS voci_totali,
       piano.voci_da_completare                             AS voci_da_completare,
       piano.pianificato_pct                                AS pianificato_pct,
       COALESCE(reale.reale_pct, 0)                          AS reale_pct,
       round(COALESCE(reale.reale_pct, 0) - piano.pianificato_pct, 1) AS delta_pct
FROM (
    SELECT cantiere_id,
           count(*)                                                        AS voci_totali,
           count(*) FILTER (WHERE fine_prevista <= current_date)           AS voci_da_completare,
           round(100.0 * count(*) FILTER (WHERE fine_prevista <= current_date) / count(*), 1)
                                                                           AS pianificato_pct
    FROM v_cronoprogramma_voci
    GROUP BY cantiere_id
) piano
LEFT JOIN (
    SELECT cantiere_id, arg_max(percentuale_avanzamento, data) AS reale_pct
    FROM v_sal
    GROUP BY cantiere_id
) reale ON reale.cantiere_id = piano.cantiere_id;

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

-- Costi mezzi: le righe fattura taggate a un mezzo, per mezzo/cantiere/natura.
-- Stesso pattern del sub-SELECT dello scostamento (righe fattura → voce di computo).
CREATE OR REPLACE VIEW v_mezzi_costi AS
SELECT mezzo_id,
       cantiere_id,
       tipo_costo,
       SUM(importo) AS costo,
       COUNT(*)     AS n_righe
FROM v_fatture_righe
WHERE mezzo_id IS NOT NULL
GROUP BY mezzo_id, cantiere_id, tipo_costo;

-- Costo pieno / TCO per mezzo: componenti derivati dall'anagrafica (ammortamento +
-- fissi → costo orario pieno per i propri) e costi documentali (fatture taggate +
-- manutenzioni). Non un numero unico: espone le componenti, oneste.
CREATE OR REPLACE VIEW v_mezzi_tco AS
SELECT m.id                                             AS mezzo_id,
       m.descrizione                                    AS descrizione,
       m.proprieta                                      AS proprieta,
       m.valore_acquisto / NULLIF(m.vita_utile_anni, 0) AS ammortamento_annuo,
       COALESCE(m.valore_acquisto / NULLIF(m.vita_utile_anni, 0), 0)
           + COALESCE(m.costi_fissi_annui, 0)           AS costo_fisso_annuo,
       (COALESCE(m.valore_acquisto / NULLIF(m.vita_utile_anni, 0), 0)
           + COALESCE(m.costi_fissi_annui, 0)) / NULLIF(m.ore_annue_stimate, 0)
                                                        AS costo_orario_pieno,
       COALESCE(fc.costo_fatture, 0)                    AS costo_fatture,
       COALESCE(mc.costo_manutenzioni, 0)               AS costo_manutenzioni,
       COALESCE(fc.costo_fatture, 0) + COALESCE(mc.costo_manutenzioni, 0)
                                                        AS costo_documentale
FROM v_mezzi m
LEFT JOIN (
    SELECT mezzo_id, SUM(costo) AS costo_fatture
    FROM v_mezzi_costi GROUP BY mezzo_id
) fc ON fc.mezzo_id = m.id
LEFT JOIN (
    SELECT mezzo_id, SUM(costo) AS costo_manutenzioni
    FROM v_manutenzioni GROUP BY mezzo_id
) mc ON mc.mezzo_id = m.id;

-- Pagamenti riletti dall'ERP (M27): stato di pagamento delle fatture sincronizzate.
-- Sola lettura ERP→WF; l'entità e' puro dato (nessun workflow).
CREATE OR REPLACE VIEW v_pagamenti AS
SELECT id,
       stato,
       dati.fattura_id     AS fattura_id,
       dati.stato          AS stato_pagamento,
       dati.importo_pagato AS importo_pagato,
       dati.data           AS data,
       dati.erp_id         AS erp_id
FROM read_json(
    '${DATA_DIR}/entities/pagamenti/*.json',
    columns = {
        id: 'VARCHAR',
        stato: 'VARCHAR',
        dati: 'STRUCT(fattura_id VARCHAR, stato VARCHAR, importo_pagato DOUBLE, data DATE, erp_id VARCHAR)'
    }
);
