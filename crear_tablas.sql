-- =====================================================================
-- Eficiencia energética: planta siderúrgica (datos UCI, Corea, 2018)
-- analizada COMO SI estuviera en España con tarifa 6.1TD (Península).
--
-- Normativa: Circular 3/2020 de la CNMC
--   - Art. 9.5: reactiva inductiva, P1 a P5, exceso sobre el 33 % de la
--     activa, calculado sobre el total del periodo de facturación (mes).
--   - Disp. Transitoria 2.ª: reactiva capacitiva, P6, cos φ > 0,98
--     "de forma horaria". Precio actual: 0 €/kVArh.
-- =====================================================================


-- ---------------------------------------------------------------------
-- FUNCIONES (macros) de la factura de reactiva inductiva
-- Se usan para la factura actual y para cada escenario de batería.
--   p = energía activa (kWh), q = reactiva inductiva (kVArh)
-- ---------------------------------------------------------------------
CREATE OR REPLACE MACRO cos_phi(p, q) AS
    p / sqrt(p ^ 2 + q ^ 2);

CREATE OR REPLACE MACRO exceso_ind(p, q, periodo) AS
    CASE WHEN periodo = 'P6' THEN 0                  -- P6 exento
         ELSE greatest(q - 0.33 * p, 0) END;         -- solo lo que supera el 33 %

CREATE OR REPLACE MACRO precio_ind(p, q, periodo) AS
    CASE WHEN exceso_ind(p, q, periodo) = 0 THEN 0
         WHEN cos_phi(p, q) < 0.80           THEN 0.062332
         ELSE                                     0.041554 END;

CREATE OR REPLACE MACRO coste_ind(p, q, periodo) AS
    exceso_ind(p, q, periodo) * precio_ind(p, q, periodo);


-- ---------------------------------------------------------------------
-- TABLA 1: consumo_15min
-- Una fila por cuarto de hora. Copia del CSV original con:
--   - la hora corregida. En el CSV:
--       a) la marca de tiempo es el FINAL del cuarto de hora ("10:00" = 9:45-10:00)
--       b) el último registro de cada día lleva la fecha de ESE día a las 00:00
--          ("01/01/2018 00:00" va después de "01/01/2018 23:45" y es 23:45-24:00
--          del día 1), así que a las filas "00:00" hay que sumarles un día.
--   - el calendario y el periodo tarifario español P1..P6
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE consumo_15min AS
WITH marca AS (
    SELECT
        strptime(date, '%d/%m/%Y %H:%M')
            + CASE WHEN date LIKE '% 00:00' THEN INTERVAL 1 DAY ELSE INTERVAL 0 DAY END AS fin,
        Usage_kWh                               AS activa_kwh,
        "Lagging_Current_Reactive.Power_kVarh"  AS reactiva_ind_kvarh,
        Leading_Current_Reactive_Power_kVarh    AS reactiva_cap_kvarh
    FROM read_csv('Steel_industry_data.csv', header = true,
                  types = {'date': 'VARCHAR'})
),
original AS (
    SELECT fin - INTERVAL 15 MINUTE AS inicio, * FROM marca
),
calendario AS (
    SELECT
        *,
        CAST(inicio AS DATE) AS fecha,
        month(inicio)        AS mes,
        hour(inicio)         AS hora,
        CASE
            WHEN month(inicio) IN (1, 2, 7, 12) THEN 'Alta'
            WHEN month(inicio) IN (3, 11)       THEN 'Media alta'
            WHEN month(inicio) IN (6, 8, 9)     THEN 'Media'
            ELSE                                     'Baja'      -- abr, may, oct
        END AS temporada,
        CASE
            WHEN isodow(inicio) >= 6 THEN 'Fin de semana'        -- 6 = sábado, 7 = domingo
            -- Festivos nacionales de fecha fija de 2018 + 6 de enero
            -- (se excluyen los sustituibles y los que no tienen fecha fija, como Viernes Santo)
            WHEN CAST(inicio AS DATE) IN (
                DATE '2018-01-01', DATE '2018-01-06', DATE '2018-05-01',
                DATE '2018-08-15', DATE '2018-10-12', DATE '2018-11-01',
                DATE '2018-12-06', DATE '2018-12-08', DATE '2018-12-25'
            ) THEN 'Festivo'
            ELSE 'Laborable'
        END AS tipo_dia
    FROM original
)
SELECT
    *,
    CASE
        -- Fines de semana, festivos y de 0 a 8 h: siempre P6
        WHEN tipo_dia <> 'Laborable' OR hora < 8 THEN 'P6'
        -- Punta (9-14 h y 18-22 h): P1 en alta, P2 en media alta, P3 en media, P4 en baja
        -- Llano (8-9 h, 14-18 h y 22-24 h): un periodo más que la punta
        ELSE 'P' || (
            CASE temporada WHEN 'Alta' THEN 1 WHEN 'Media alta' THEN 2 WHEN 'Media' THEN 3 ELSE 4 END
            + CASE WHEN hora BETWEEN 9 AND 13 OR hora BETWEEN 18 AND 21 THEN 0 ELSE 1 END
        )
    END AS periodo
FROM calendario
ORDER BY inicio;


-- ---------------------------------------------------------------------
-- TABLA 2: capacitiva_horaria
-- Una fila por hora de P6. La norma exige cos φ capacitivo > 0,98 hora a
-- hora, es decir: reactiva capacitiva <= tan(acos 0,98) x activa (~20 %).
-- El exceso se calcula por analogía con la inductiva (lo que supera el
-- límite). Como el precio vigente es 0 €/kVArh, el coste sale 0.
--
-- CONCLUSIÓN: aunque hoy no se paga, la planta incumple el 0,98 en el 46 %
-- de las horas de fin de semana y el 36 % de las de festivos (de noche en
-- laborables solo el 1 %). También va a capacitivo en las paradas del día
-- (12 h y 21 h). Hay que desconectar los condensadores los fines de semana,
-- los festivos y en las paradas de producción.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE capacitiva_horaria AS
WITH por_hora AS (
    SELECT
        date_trunc('hour', inicio) AS hora_inicio,
        mes,
        SUM(activa_kwh)            AS activa_kwh,
        SUM(reactiva_cap_kvarh)    AS reactiva_cap_kvarh
    FROM consumo_15min
    WHERE periodo = 'P6'
    GROUP BY date_trunc('hour', inicio), mes
)
SELECT
    *,
    CASE WHEN activa_kwh = 0 AND reactiva_cap_kvarh = 0 THEN NULL
         ELSE activa_kwh / sqrt(activa_kwh ^ 2 + reactiva_cap_kvarh ^ 2)
    END                                                               AS cos_phi_cap,
    greatest(reactiva_cap_kvarh - tan(acos(0.98)) * activa_kwh, 0)    AS exceso_cap_kvarh,
    reactiva_cap_kvarh > tan(acos(0.98)) * activa_kwh                 AS incumple_098,
    greatest(reactiva_cap_kvarh - tan(acos(0.98)) * activa_kwh, 0) * 0.0 AS coste_cap_eur  -- precio vigente: 0 €/kVArh
FROM por_hora
ORDER BY hora_inicio;


-- ---------------------------------------------------------------------
-- TABLA 3: simulacion_15min
-- Una fila por cuarto de hora. Simula una batería de condensadores
-- REGULADA de 50, 100 o 150 kVAr añadida a la compensación actual:
--   - kvar_faltan: kVAr que faltan en ese cuarto de hora para llegar a
--     cos φ 0,95 (el mínimo para no pagar). La reactiva de un cuarto de
--     hora son kVArh; x 4 para pasar a kVAr (potencia).
--   - reactiva_ind_X: reactiva inductiva que quedaría si la batería
--     compensa lo que falta, hasta un máximo de X kVAr.
-- Al ser regulada, solo compensa lo que falta: nunca lleva la planta a
-- capacitivo. Supuesto: los condensadores actuales siguen funcionando igual.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE simulacion_15min AS
WITH faltan AS (
    SELECT
        inicio, mes, periodo, activa_kwh, reactiva_ind_kvarh,
        greatest(4 * (reactiva_ind_kvarh - tan(acos(0.95)) * activa_kwh), 0) AS kvar_faltan
    FROM consumo_15min
)
SELECT
    inicio, mes, periodo, activa_kwh, reactiva_ind_kvarh,
    round(kvar_faltan, 2)                                            AS kvar_faltan,
    round(reactiva_ind_kvarh - least(kvar_faltan,  50) / 4, 3)       AS reactiva_ind_50,
    round(reactiva_ind_kvarh - least(kvar_faltan, 100) / 4, 3)       AS reactiva_ind_100,
    round(reactiva_ind_kvarh - least(kvar_faltan, 150) / 4, 3)       AS reactiva_ind_150
FROM faltan
ORDER BY inicio;


-- ---------------------------------------------------------------------
-- TABLA 4: factura_mensual
-- Una fila por mes y periodo tarifario. La inductiva se calcula con los
-- totales del mes de cada periodo (P1..P5; P6 exento).
--   - Columnas sin sufijo: factura ACTUAL.
--   - Columnas _50, _100, _150: factura con la batería de ese tamaño.
-- La capacitiva se trae sumada por mes desde la tabla 2 (solo P6).
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE factura_mensual AS
WITH totales AS (
    SELECT
        mes,
        periodo,
        SUM(activa_kwh)         AS p,
        SUM(reactiva_ind_kvarh) AS q,
        SUM(reactiva_ind_50)    AS q50,
        SUM(reactiva_ind_100)   AS q100,
        SUM(reactiva_ind_150)   AS q150
    FROM simulacion_15min
    GROUP BY mes, periodo
),
capacitiva_mes AS (
    SELECT
        mes,
        'P6'                                  AS periodo,
        COUNT(*) FILTER (WHERE incumple_098)  AS horas_incumple_cap,
        SUM(exceso_cap_kvarh)                 AS exceso_cap_kvarh,
        SUM(coste_cap_eur)                    AS coste_cap_eur
    FROM capacitiva_horaria
    GROUP BY mes
)
SELECT
    t.mes,
    t.periodo,
    -- Situación actual
    round(t.p, 1)                                AS activa_kwh,
    round(t.q, 1)                                AS reactiva_ind_kvarh,
    round(cos_phi(t.p, t.q), 3)                  AS cos_phi_ind,
    round(exceso_ind(t.p, t.q, t.periodo), 1)    AS exceso_ind_kvarh,
    precio_ind(t.p, t.q, t.periodo)              AS precio_ind_eur_kvarh,
    round(coste_ind(t.p, t.q, t.periodo), 2)     AS coste_ind_eur,
    COALESCE(c.horas_incumple_cap, 0)            AS horas_incumple_cap,
    round(COALESCE(c.exceso_cap_kvarh, 0), 1)    AS exceso_cap_kvarh,
    round(COALESCE(c.coste_cap_eur, 0), 2)       AS coste_cap_eur,
    -- Con batería regulada de 50, 100 y 150 kVAr
    round(cos_phi(t.p, t.q50), 3)                AS cos_phi_ind_50,
    round(coste_ind(t.p, t.q50, t.periodo), 2)   AS coste_ind_50,
    round(cos_phi(t.p, t.q100), 3)               AS cos_phi_ind_100,
    round(coste_ind(t.p, t.q100, t.periodo), 2)  AS coste_ind_100,
    round(cos_phi(t.p, t.q150), 3)               AS cos_phi_ind_150,
    round(coste_ind(t.p, t.q150, t.periodo), 2)  AS coste_ind_150
FROM totales t
LEFT JOIN capacitiva_mes c USING (mes, periodo)
ORDER BY t.mes, t.periodo;
