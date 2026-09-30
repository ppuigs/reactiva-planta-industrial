"""
Genera el proyecto de Power BI (formato PBIP, en texto plano) a partir de los CSV de datos/.
    python generar_powerbi.py
Después se abre powerbi/Reactiva.pbip con Power BI Desktop y se pulsa "Actualizar".

Formato PBIP:
  - modelo semántico en TMDL  (tablas, columnas, medidas DAX)
  - informe en PBIR           (páginas y visuales en JSON)
Referencia: https://learn.microsoft.com/power-bi/developer/projects/projects-overview
"""
import hashlib
import json
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "powerbi"
NAME = "Reactiva"
DATA_DIR = str((ROOT / "datos").resolve())
MODEL_DIR = OUT / f"{NAME}.SemanticModel"
REPORT_DIR = OUT / f"{NAME}.Report"
PAGE_W, PAGE_H = 1280, 720


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # UTF-8 sin BOM y saltos de línea CRLF, como hace Power BI Desktop
    path.write_bytes(text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))


def write_json(path: Path, obj) -> None:
    write(path, json.dumps(obj, indent=2, ensure_ascii=False))


def oid(label: str) -> str:
    """Identificador de 20 caracteres, siempre el mismo para la misma etiqueta."""
    return hashlib.sha1(label.encode()).hexdigest()[:20]


def guid(label: str) -> str:
    """GUID determinista (lineageTag) a partir de una etiqueta."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "reactiva/" + label))


def lit(value) -> dict:
    """Literal de PBIR: texto → 'x', número → 12D, booleano → true."""
    if isinstance(value, bool):
        v = "true" if value else "false"
    elif isinstance(value, (int, float)):
        v = f"{value}D"
    else:
        v = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": v}}}


# ----------------------------------------------------------------------------
# 1) MODELO SEMÁNTICO (TMDL)
# ----------------------------------------------------------------------------
# tipo: (tipo TMDL, tipo M, formato)
T = {
    "str": ("string", "type text", None),
    "int": ("int64", "Int64.Type", "0"),
    "dbl": ("double", "type number", "#,0.00"),
    "dt": ("dateTime", "type datetime", "yyyy-mm-dd hh:nn"),
    "date": ("dateTime", "type date", "yyyy-mm-dd"),
}
MESES = '{"Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"}'

F, C = "factura_mensual", "consumo_15min"

TABLES = {
    F: {
        "file": "factura_mensual.csv",
        "columns": [
            ("mes", "int"), ("periodo", "str"), ("activa_kwh", "dbl"), ("reactiva_ind_kvarh", "dbl"),
            ("cos_phi_ind", "dbl"), ("exceso_ind_kvarh", "dbl"), ("precio_ind_eur_kvarh", "dbl"),
            ("coste_ind_eur", "dbl"), ("horas_incumple_cap", "int"), ("exceso_cap_kvarh", "dbl"),
            ("coste_cap_eur", "dbl"),
            ("cos_phi_ind_50", "dbl"), ("coste_ind_50", "dbl"),
            ("cos_phi_ind_100", "dbl"), ("coste_ind_100", "dbl"),
            ("cos_phi_ind_150", "dbl"), ("coste_ind_150", "dbl"),
        ],
        "formats": {"cos_phi_ind": "0.000", "cos_phi_ind_50": "0.000", "cos_phi_ind_100": "0.000",
                    "cos_phi_ind_150": "0.000", "precio_ind_eur_kvarh": "0.000000"},
        "sort_by": {"mes_nombre": "mes"},
        "measures": [
            ("Coste actual €", f"SUM({F}[coste_ind_eur])", "#,0 €"),
            ("Coste con 50 kVAr €", f"SUM({F}[coste_ind_50])", "#,0 €"),
            ("Coste con 100 kVAr €", f"SUM({F}[coste_ind_100])", "#,0 €"),
            ("Coste con 150 kVAr €", f"SUM({F}[coste_ind_150])", "#,0 €"),
            ("Ahorro con 100 kVAr €", "[Coste actual €] - [Coste con 100 kVAr €]", "#,0 €"),
            ("Energía activa MWh", f"SUM({F}[activa_kwh]) / 1000", "#,0"),
            ("Horas P6 que incumplen 0,98", f"SUM({F}[horas_incumple_cap])", "#,0"),
            ("cos φ actual", f"AVERAGE({F}[cos_phi_ind])", "0.000"),
            ("cos φ con 50 kVAr", f"AVERAGE({F}[cos_phi_ind_50])", "0.000"),
            ("cos φ con 100 kVAr", f"AVERAGE({F}[cos_phi_ind_100])", "0.000"),
            ("cos φ con 150 kVAr", f"AVERAGE({F}[cos_phi_ind_150])", "0.000"),
            # Color de la matriz según los tramos de precio de la tarifa (sin datos: sin color)
            #   verde  >= 0,95        -> 0 €/kVArh
            #   ámbar  0,80 - 0,95    -> 0,041554 €/kVArh
            #   rojo   < 0,80         -> 0,062332 €/kVArh
            ("Color cos φ", "VAR c = [cos φ actual] RETURN IF(ISBLANK(c), BLANK(), "
                            "IF(c >= 0.95, \"#CDEBD3\", IF(c >= 0.80, \"#FFE4A3\", \"#F6B3AE\")))", None),
        ],
    },
    C: {
        "file": "consumo_15min.csv",
        "columns": [
            ("inicio", "dt"), ("fin", "dt"), ("activa_kwh", "dbl"), ("reactiva_ind_kvarh", "dbl"),
            ("reactiva_cap_kvarh", "dbl"), ("fecha", "date"), ("mes", "int"), ("hora", "int"),
            ("temporada", "str"), ("tipo_dia", "str"), ("periodo", "str"),
        ],
        "formats": {},
        "sort_by": {"mes_nombre": "mes"},
        "measures": [
            ("Potencia media kW", f"AVERAGE({C}[activa_kwh]) * 4", "#,0"),
            ("Inductiva kVAr medios", f"AVERAGE({C}[reactiva_ind_kvarh]) * 4", "#,0"),
            ("Capacitiva kVAr medios", f"AVERAGE({C}[reactiva_cap_kvarh]) * 4", "#,0"),
        ],
    },
}
ADDED = [("mes_nombre", "str")]   # columna que se añade en Power Query (nombre del mes)


def m_query(spec: dict) -> str:
    """Consulta Power Query (M): lee el CSV, pone tipos y añade el nombre del mes."""
    n = len(spec["columns"])
    types = ", ".join(f'{{"{c}", {T[t][1]}}}' for c, t in spec["columns"])
    return "\n".join([
        "let",
        f'    Source = Csv.Document(File.Contents(DataFolder & "\\{spec["file"]}"), '
        f'[Delimiter=",", Columns={n}, Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
        '    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
        f'    Typed = Table.TransformColumnTypes(Headers, {{{types}}}, "en-US"),',
        f'    Meses = Table.AddColumn(Typed, "mes_nombre", each {MESES}{{[mes] - 1}}, type text)',
        "in",
        "    Meses",
    ])


def tmdl_table(table: str, spec: dict) -> str:
    out = [f"table {table}", f"\tlineageTag: {guid('table/' + table)}", ""]
    for name, expr, fmt in spec["measures"]:
        out.append(f"\tmeasure '{name}' = {expr}")
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out += [f"\t\tlineageTag: {guid(f'measure/{table}/{name}')}", ""]
    for col, t in spec["columns"] + ADDED:
        dtype, _, fmt = T[t]
        fmt = spec["formats"].get(col, fmt)
        out += [f"\tcolumn {col}", f"\t\tdataType: {dtype}"]
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out += [f"\t\tlineageTag: {guid(f'column/{table}/{col}')}", "\t\tsummarizeBy: none",
                f"\t\tsourceColumn: {col}"]
        if col in spec["sort_by"]:
            out.append(f"\t\tsortByColumn: {spec['sort_by'][col]}")
        out += ["", "\t\tannotation SummarizationSetBy = User", ""]
    m = "\n".join("\t\t\t" + line for line in m_query(spec).splitlines())
    out += [f"\tpartition {table} = m", "\t\tmode: import", "\t\tsource =", m, "",
            "\tannotation PBI_ResultType = Table", ""]
    return "\n".join(out)


def build_model() -> None:
    write_json(MODEL_DIR / "definition.pbism", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2",
        "settings": {"qnaEnabled": True},
    })
    d = MODEL_DIR / "definition"
    # 1606: nivel que escribe Power BI Desktop al guardar (no se puede bajar después)
    write(d / "database.tmdl", "database\n\tcompatibilityLevel: 1606\n")
    order = json.dumps(list(TABLES) + ["DataFolder"])
    write(d / "model.tmdl", "\n".join([
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tsourceQueryCulture: en-US",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
        f"annotation PBI_QueryOrder = {order}",
        "",
    ] + [f"ref table {t}" for t in TABLES] + [""]))
    # Parámetro con la carpeta de los CSV: si mueves el proyecto, cámbialo aquí o en Power Query
    write(d / "expressions.tmdl", "\n".join([
        f'expression DataFolder = "{DATA_DIR}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
        f"\tlineageTag: {guid('expression/DataFolder')}",
        "",
        "\tannotation PBI_ResultType = Text",
        "",
    ]))
    for t, spec in TABLES.items():
        write(d / "tables" / f"{t}.tmdl", tmdl_table(t, spec))
    # Sin relaciones: cada visual usa una sola tabla


# ----------------------------------------------------------------------------
# 2) INFORME (PBIR)
# ----------------------------------------------------------------------------
def col(table: str, name: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def mea(table: str, name: str) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def proj(field: dict, display: str | None = None) -> dict:
    kind = "Column" if "Column" in field else "Measure"
    table, prop = field[kind]["Expression"]["SourceRef"]["Entity"], field[kind]["Property"]
    p = {"field": field, "queryRef": f"{table}.{prop}", "nativeQueryRef": display or prop}
    if display:
        p["displayName"] = display
    return p


def container(title: str | None, subtitle: str | None = None) -> dict:
    return {
        "title": [{"properties": {"show": lit(title is not None), "text": lit(title or "")}}],
        "subTitle": [{"properties": {"show": lit(subtitle is not None), "text": lit(subtitle or "")}}],
        "background": [{"properties": {"show": lit(True)}}],
        "border": [{"properties": {"show": lit(True)}}],
    }


def visual(page: str, label: str, pos: tuple, vtype: str, roles: dict | None = None,
           title: str | None = None, objects: dict | None = None, filters: list | None = None,
           subtitle: str | None = None) -> dict:
    x, y, w, h = pos
    v = {"visualType": vtype, "drillFilterOtherVisuals": True}
    if roles:
        v["query"] = {"queryState": {role: {"projections": ps} for role, ps in roles.items()}}
    if objects:
        v["objects"] = objects
    v["visualContainerObjects"] = container(title, subtitle)
    out = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.4.0/schema.json",
        "name": oid(f"{page}/{label}"),
        "position": {"x": x, "y": y, "z": 0, "width": w, "height": h},
        "visual": v,
    }
    if filters:
        out["filterConfig"] = {"filters": filters}
    return out


def textbox(page: str, label: str, pos: tuple, lines, size: int = 11, bold_first: bool = False) -> dict:
    """Cuadro de texto. `lines` puede ser un texto o una lista (un párrafo por elemento)."""
    lines = [lines] if isinstance(lines, str) else lines
    paragraphs = []
    for i, text in enumerate(lines):
        style = {"fontSize": f"{size}pt"}
        if bold_first and i == 0:
            style["fontWeight"] = "bold"
        paragraphs.append({"textRuns": [{"value": text, "textStyle": style}]})
    v = visual(page, label, pos, "textbox", objects={"general": [{"properties": {"paragraphs": paragraphs}}]})
    v["visual"]["visualContainerObjects"] = {
        "title": [{"properties": {"show": lit(False)}}],
        "background": [{"properties": {"show": lit(False)}}],
        "border": [{"properties": {"show": lit(False)}}],
    }
    return v


def card(page: str, label: str, pos: tuple, measure: dict) -> dict:
    return visual(page, label, pos, "card", {"Values": [proj(measure)]},
                  objects={"labels": [{"properties": {"fontSize": lit(24)}}]})


def filter_in(table: str, column: str, values: list[str]) -> dict:
    """Filtro de visual: columna IN (valores)."""
    return {
        "name": oid(f"filter/{table}/{column}/{'-'.join(values)}"),
        "field": col(table, column),
        "type": "Categorical",
        "filter": {
            "Version": 2,
            "From": [{"Name": "t", "Entity": table, "Type": 0}],
            "Where": [{"Condition": {"In": {
                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": column}}],
                "Values": [[{"Literal": {"Value": f"'{v}'"}}] for v in values],
            }}}],
        },
    }


def color_by_measure(color_measure: dict, metadata: str) -> dict:
    """Formato condicional de fondo: el color lo devuelve una medida DAX (texto "#RRGGBB")."""
    return {"values": [{
        "properties": {"backColor": {"solid": {"color": {"expr": color_measure}}}},
        "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": metadata},
    }]}


def lit_int(value: int) -> dict:
    """Literal entero de PBIR (sufijo L), p. ej. para la precisión de las etiquetas."""
    return {"expr": {"Literal": {"Value": f"{value}L"}}}


NO_AXIS_TITLE = {"valueAxis": [{"properties": {"showAxisTitle": lit(False)}}]}


LEGEND = {"legend": [{"properties": {"show": lit(True), "position": lit("Top")}}]}
P1_P5 = ["P1", "P2", "P3", "P4", "P5"]


def page_actual() -> tuple[str, list]:
    pg = "actual"
    return "Situación actual", [
        textbox(pg, "title", (20, 10, 1240, 45),
                "Energía reactiva: situación actual (planta supuesta en España, tarifa 6.1TD, 2018)", 18, True),
        card(pg, "coste", (21, 64, 299, 102), mea(F, "Coste actual €")),
        card(pg, "energia", (340, 64, 300, 102), mea(F, "Energía activa MWh")),
        card(pg, "horas_cap", (660, 64, 300, 102), mea(F, "Horas P6 que incumplen 0,98")),
        textbox(pg, "nota", (981, 64, 280, 85), [
            "Coste: penalización por reactiva inductiva (P1-P5).",
            "La capacitiva (P6) incumple el límite, pero hoy se paga a 0 €.",
        ], 10),
        visual(pg, "coste_mes", (21, 180, 620, 276), "columnChart",
               {"Category": [proj(col(F, "mes_nombre"), "Mes")],
                "Y": [proj(mea(F, "Coste actual €"), "Coste €")],
                "Series": [proj(col(F, "periodo"), "Periodo")]},
               title="Coste de la reactiva por mes y periodo (€)", objects=LEGEND),
        visual(pg, "matriz", (660, 180, 601, 276), "pivotTable",
               {"Rows": [proj(col(F, "periodo"), "Periodo")],
                "Columns": [proj(col(F, "mes_nombre"), "Mes")],
                "Values": [proj(mea(F, "cos φ actual"), "cos φ")]},
               title="Factor de potencia (cos φ) mensual por periodo",
               subtitle="Verde ≥ 0,95: 0 €  ·  Ámbar 0,80-0,95: 0,042 €/kVArh  ·  Rojo < 0,80: 0,062 €/kVArh",
               objects={"subTotals": [{"properties": {"rowSubtotals": lit(False), "columnSubtotals": lit(False)}}],
                        "grid": [{"properties": {"gridVertical": lit(False), "gridHorizontal": lit(False),
                                                 "rowPadding": lit(6)}}],
                        "columnHeaders": [{"properties": {"fontSize": lit(10), "alignment": lit("Center")}}],
                        "rowHeaders": [{"properties": {"fontSize": lit(10)}}],
                        "values": [{"properties": {"fontSize": lit(10)}}]
                                  + color_by_measure(mea(F, "Color cos φ"), f"{F}.cos φ actual")["values"]},
               filters=[filter_in(F, "periodo", P1_P5)]),
        visual(pg, "perfil", (21, 469, 1240, 231), "lineClusteredColumnComboChart",
               {"Category": [proj(col(C, "hora"), "Hora")],
                "Y": [proj(mea(C, "Potencia media kW"), "Potencia activa (kW)")],
                "Y2": [proj(mea(C, "Inductiva kVAr medios"), "Inductiva (kVAr)"),
                       proj(mea(C, "Capacitiva kVAr medios"), "Capacitiva (kVAr)")]},
               title="Distribución de potencias, media por hora",
               subtitle="Días laborables. Cuando la planta para (12 h y 21 h), los condensadores siguen "
                        "conectados y la reactiva pasa a capacitiva",
               objects={**LEGEND, "categoryAxis": [{"properties": {"axisType": lit("Categorical")}}]},
               filters=[filter_in(C, "tipo_dia", ["Laborable"])]),
    ]


def page_propuesta() -> tuple[str, list]:
    pg = "propuesta"
    return "Propuesta", [
        textbox(pg, "title", (20, 10, 1240, 45),
                "Propuesta: batería de condensadores regulada", 18, True),
        visual(pg, "costes", (20, 65, 620, 300), "clusteredColumnChart",
               {"Y": [proj(mea(F, "Coste actual €"), "Actual"),
                      proj(mea(F, "Coste con 50 kVAr €"), "+50 kVAr"),
                      proj(mea(F, "Coste con 100 kVAr €"), "+100 kVAr"),
                      proj(mea(F, "Coste con 150 kVAr €"), "+150 kVAr")]},
               title="Coste anual de la reactiva según la batería añadida (€)",
               objects={**LEGEND, **NO_AXIS_TITLE,
                        "labels": [{"properties": {"show": lit(True), "labelDisplayUnits": lit(1),
                                                   "labelPrecision": lit_int(0)}}]}),
        card(pg, "ahorro", (660, 65, 290, 120), mea(F, "Ahorro con 100 kVAr €")),
        card(pg, "coste100", (970, 65, 290, 120), mea(F, "Coste con 100 kVAr €")),
        visual(pg, "cosphi", (660, 200, 600, 265), "clusteredColumnChart",
               {"Category": [proj(col(F, "periodo"), "Periodo")],
                "Y": [proj(mea(F, "cos φ actual"), "Actual"),
                      proj(mea(F, "cos φ con 50 kVAr"), "+50 kVAr"),
                      proj(mea(F, "cos φ con 100 kVAr"), "+100 kVAr"),
                      proj(mea(F, "cos φ con 150 kVAr"), "+150 kVAr")]},
               title="cos φ por periodo (media de los meses); línea: límite de 0,95",
               objects={**LEGEND,
                        "valueAxis": [{"properties": {"start": lit(0.85), "end": lit(1),
                                                      "showAxisTitle": lit(False)}}],
                        "y1AxisReferenceLine": [{"properties": {
                            "show": lit(True), "value": lit(0.95), "style": lit("dashed"),
                            "lineColor": {"solid": {"color": lit("#C0392B")}},
                            "displayName": lit("Límite 0,95"), "dataLabelShow": lit(True)},
                            "selector": {"id": "1"}}]},
               filters=[filter_in(F, "periodo", P1_P5)]),
        textbox(pg, "recomendacion", (21, 380, 620, 210), [
            "Recomendación",
            "1. Añadir una batería de condensadores REGULADA de unos 100 kVAr: la penalización baja "
            "de 4.032 € a 13 € al año (−99,7 %). Con 50 kVAr ya se ahorra el 84 %; pasar a 150 kVAr "
            "solo ahorra 13 € más.",
            "2. Regulación automática por escalones: conectar cuando sube la carga y desconectar cuando baja.",
            "3. Desconectar los condensadores los fines de semana, los festivos y en las paradas "
            "(12 h y 21 h). Hoy la planta incumple el 0,98 capacitivo en el 26 % de las horas de P6: "
            "no se paga (0 €/kVArh), pero sube la tensión y podría penalizarse en el futuro.",
        ], 11, bold_first=True),
        textbox(pg, "supuestos", (660, 480, 600, 220), [
            "Supuestos",
            "• Datos reales de una planta siderúrgica coreana (UCI, 2018), analizados como si estuviera "
            "en España con tarifa 6.1TD (Circular 3/2020 de la CNMC).",
            "• Inductiva facturada con los totales del mes de cada periodo (P1-P5); P6 exento.",
            "• La batería simulada compensa cada cuarto de hora hasta cos φ 0,95, sin pasar a "
            "capacitivo, y se suma a los condensadores actuales.",
            "• No incluye el precio de la batería: hay que pedir presupuesto para calcular la amortización.",
        ], 10, bold_first=True),
    ]


def build_report() -> None:
    write_json(REPORT_DIR / "definition.pbir", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}},
    })
    d = REPORT_DIR / "definition"
    write_json(d / "version.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0",
    })
    write_json(d / "report.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.0.0/schema.json",
        "themeCollection": {"baseTheme": {
            "name": "CY24SU10",
            "reportVersionAtImport": {"visual": "1.8.95", "report": "2.0.95", "page": "1.3.95"},
            "type": "SharedResources"}},
        "resourcePackages": [{"name": "SharedResources", "type": "SharedResources",
                              "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                     "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True},
    })
    names = []
    for display, visuals in (page_actual(), page_propuesta()):
        pname = oid(f"page/{display}")
        names.append(pname)
        write_json(d / "pages" / pname / "page.json", {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json",
            "name": pname, "displayName": display, "displayOption": "FitToPage",
            "height": PAGE_H, "width": PAGE_W,
        })
        for z, v in enumerate(visuals):
            v["position"]["z"] = z * 1000
            write_json(d / "pages" / pname / "visuals" / v["name"] / "visual.json", v)
    write_json(d / "pages" / "pages.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": names, "activePageName": names[0],
    })


def build() -> None:
    # Solo se regeneran las definiciones; se conserva .pbi/ (caché de datos de Power BI)
    for d in (MODEL_DIR / "definition", REPORT_DIR / "definition"):
        if d.exists():
            shutil.rmtree(d)
    build_model()
    build_report()
    write_json(OUT / f"{NAME}.pbip", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    })
    n = sum(1 for p in OUT.rglob("*") if p.is_file())
    print(f"Proyecto de Power BI generado en {OUT} ({n} archivos)")


if __name__ == "__main__":
    build()
