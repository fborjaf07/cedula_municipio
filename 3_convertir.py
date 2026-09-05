#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
3_convertir.py — Junta los Partida XLS de todas las direcciones en un JSON.

No calcula nada de la regla del 65 %: solo pasa los XLS a un formato que se
pueda leer sin Excel, conservando cada cifra tal como la imprimio eGob. El
calculo va aparte, para que se pueda revisar la conversion por separado de
la interpretacion legal.

Uso:
    python3 3_convertir.py --datos datos --salida datos-municipio.json
"""

import argparse
import glob
import json
import os
import sys
import re
from datetime import datetime, timezone, timedelta

import leer_partida_xls as LP
import leer_detalle_xls as LD

TZ = timezone(timedelta(hours=-5))

# Ventana de la verificacion excepcional de 2026 (Decreto 392, Transitoria
# Primera). No es el ejercicio completo: se mide lo devengado entre estas dos
# fechas, y eGob no acepta filtrarlas en la consulta, asi que hay que leer la
# fecha de cada movimiento del detalle.
VENTANA = ("2026-06-01", "2026-11-30")

MESES_ES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre",
            "diciembre"]


def codigo_de(ruta):
    """partidas_2026_3_6.xls -> 2026.3.6"""
    base = os.path.basename(ruta)
    m = re.search(r"partidas_(\d{4})_([\d_]+)\.xls$", base)
    if m:
        return m.group(1) + "." + m.group(2).strip("_").replace("_", ".")
    return base


def catalogo():
    for ruta in ("direcciones.json", os.path.join("datos", "direcciones.json")):
        if os.path.exists(ruta):
            with open(ruta, encoding="utf-8") as f:
                return {d["codigo"]: d for d in json.load(f)}
    return {}


def cargar_detalle(carpeta):
    """Lee datos/detalle/*.xls e indexa los movimientos por subpartida.

    Puede haber un archivo por direccion o varios; se tratan igual. Si una
    subpartida aparece en mas de un archivo se conserva la del mas reciente,
    que es la que refleja el ultimo corte.
    """
    bloques, leidos, avisos = {}, 0, []
    # Recursivo: segun como se armo el artefacto, el detalle puede quedar en
    # datos/detalle/ o un nivel mas abajo, en datos/datos/detalle/.
    rutas = sorted(set(glob.glob(os.path.join(carpeta, "*.xls"))
                       + glob.glob(os.path.join(carpeta, "**", "*.xls"),
                                   recursive=True)),
                   key=os.path.getmtime)
    for ruta in rutas:
        # Los Partida XLS no son detalle; leerlos aqui solo genera avisos.
        if os.path.basename(ruta).startswith("partidas_"):
            continue
        try:
            d = LD.leer(ruta)
        except Exception as e:
            avisos.append(f"{os.path.basename(ruta)}: {str(e)[:120]}")
            continue
        leidos += 1
        for b in d.get("bloques", []):
            if b.get("movimientos"):
                bloques[b["codigo"]] = b
    return bloques, leidos, avisos


def mensual(direcciones, bloques):
    """Serie mensual por direccion, fechada por el movimiento.

    No sirve fechar por la certificacion: una obra certificada en enero y
    pagada en julio no es pago de enero. Cada movimiento cuenta en el mes en
    que ocurrio, que es lo que permite ver el ritmo real de pago.
    """
    campos = ("certificado", "comprometido", "devengado", "pagado")

    # de que direccion y partida general cuelga cada subpartida
    duenio = {}
    for d in direcciones:
        for p in d["partidas"]:
            for s in p.get("subs_codigos", []):
                duenio[s] = (d["codigo"], p["codigo"])

    meses = {}
    for cod, b in bloques.items():
        dirc, part = duenio.get(cod, ("", cod[:8]))
        for m in b["movimientos"]:
            f = m.get("fecha") or ""
            if len(f) < 7:
                continue
            mes = f[:7]
            r = meses.setdefault(mes, {"n": 0, "anulaciones": 0,
                                       "por_direccion": {}, "por_grupo": {},
                                       "por_partida": {},
                                       **{k: 0.0 for k in campos}})
            r["n"] += 1
            if m["certificado"] < 0 or m["comprometido"] < 0:
                r["anulaciones"] += 1
            for k in campos:
                r[k] += m[k]
            pd = r["por_direccion"].setdefault(dirc, {k: 0.0 for k in campos})
            pg = r["por_grupo"].setdefault(cod[:2], {k: 0.0 for k in campos})
            # clave dir|partida: permite filtrar la cedula por mes
            pp = r["por_partida"].setdefault(dirc + "|" + part,
                                             {k: 0.0 for k in campos})
            for k in campos:
                pd[k] += m[k]
                pg[k] += m[k]
                pp[k] += m[k]

    salida, acum = [], {k: 0.0 for k in campos}
    for mes in sorted(meses):
        r = meses[mes]
        for k in campos:
            acum[k] += r[k]
        aa, mm = mes.split("-")
        fila = {
            "mes": mes,
            "etiqueta": f"{MESES_ES[int(mm)]} {aa}",
            "corto": MESES_ES[int(mm)][:3].capitalize(),
            "movimientos": r["n"],
            "anulaciones": r["anulaciones"],
            "en_ventana": VENTANA[0][:7] <= mes <= VENTANA[1][:7],
        }
        fila.update({k: round(r[k], 2) for k in campos})
        fila.update({"acum_" + k: round(acum[k], 2) for k in campos})
        fila["por_direccion"] = {d: {k: round(v[k], 2) for k in campos}
                                 for d, v in r["por_direccion"].items()}
        fila["por_grupo"] = {g: {k: round(v[k], 2) for k in campos}
                             for g, v in r["por_grupo"].items()}
        fila["por_partida"] = {c: {k: round(v[k], 2) for k in campos}
                               for c, v in r["por_partida"].items()
                               if any(abs(v[k]) > 0.004 for k in campos)}
        salida.append(fila)
    return salida


def indicador_ventana(direcciones, bloques):
    """Cumplimiento de 2026 sobre el devengado de la ventana legal.

    Reglamento art. 6: gasto computable devengado sobre egresos no
    financieros devengados. Transitoria Primera: del 1 de junio al 30 de
    noviembre de 2026, al menos el 65 %.
    """
    from clasificador import es_computable, en_denominador

    dueno = {}
    for d in direcciones:
        for p in d["partidas"]:
            for s in p.get("subs_codigos", []):
                dueno[s] = (d["codigo"], p["codigo"])

    num = den = 0.0
    por_dir, por_grupo = {}, {}
    ini, fin = VENTANA
    for cod, b in bloques.items():
        dirc, part = dueno.get(cod, ("", cod[:8]))
        comp = es_computable(part)
        deno = en_denominador(part)
        for m in b["movimientos"]:
            f = m.get("fecha") or ""
            if not (ini <= f <= fin):
                continue
            dev = m["devengado"]
            if not deno:
                continue
            den += dev
            if comp:
                num += dev
            pd = por_dir.setdefault(dirc, {"num": 0.0, "den": 0.0})
            pd["den"] += dev
            if comp:
                pd["num"] += dev
            pg = por_grupo.setdefault(part[:2], {"num": 0.0, "den": 0.0})
            pg["den"] += dev
            if comp:
                pg["num"] += dev

    return {
        "desde": ini, "hasta": fin, "umbral": 65,
        "num": round(num, 2), "den": round(den, 2),
        "pct": round(num / den * 100, 2) if den > 0 else None,
        "por_direccion": {k: {"num": round(v["num"], 2),
                              "den": round(v["den"], 2),
                              "pct": round(v["num"] / v["den"] * 100, 2)
                              if v["den"] > 0 else None}
                          for k, v in por_dir.items()},
        "por_grupo": {k: {"num": round(v["num"], 2),
                          "den": round(v["den"], 2)}
                      for k, v in por_grupo.items()},
    }


def verificar(direcciones, total, previo):
    """Cuadres del codificado. Devuelve (errores, alertas).

    Un error significa que las cifras no son confiables y el consolidado no
    debe publicarse. Una alerta se reporta pero no bloquea.
    """
    errores, alertas = [], []
    TOL = 1.0  # un dolar: absorbe el redondeo de eGob sin tapar diferencias

    for d in direcciones:
        t, cod = d["total"], d["codigo"]

        # 1. Identidad presupuestaria: codificado = asignacion + reformas
        esperado = t["asignacion"] + t["reformas"]
        if abs(esperado - t["codificado"]) > TOL:
            errores.append(
                f"{cod}: codificado {t['codificado']:,.2f} no es asignacion "
                f"{t['asignacion']:,.2f} + reformas {t['reformas']:,.2f} "
                f"(difiere en {t['codificado'] - esperado:,.2f})")

        # 2. Las partidas deben sumar el total que declara el propio XLS
        suma = round(sum(x.get("codificado", 0.0) for x in d["partidas"]), 2)
        if abs(suma - t["codificado"]) > TOL:
            errores.append(
                f"{cod}: las {len(d['partidas'])} partidas suman "
                f"{suma:,.2f} pero el total del XLS dice "
                f"{t['codificado']:,.2f} (difiere en {suma - t['codificado']:,.2f})")

        # 3. Las subpartidas deben sumar el codificado de su partida
        porpadre = {}
        for s in d.get("subpartidas", []):
            porpadre.setdefault(s.get("padre"), 0.0)
            porpadre[s["padre"]] += s.get("codificado", 0.0)
        for x in d["partidas"]:
            if x["codigo"] not in porpadre:
                continue
            sub = round(porpadre[x["codigo"]], 2)
            if abs(sub - x.get("codificado", 0.0)) > TOL:
                alertas.append(
                    f"{cod} partida {x['codigo']}: subpartidas suman "
                    f"{sub:,.2f} vs. {x.get('codificado', 0.0):,.2f} de la partida")

        # 4. Coherencia de la cadena de ejecucion
        if t["certificado"] - t["codificado"] > TOL:
            errores.append(f"{cod}: certificado supera el codificado")
        if t["devengado"] - t["comprometido"] > TOL:
            alertas.append(f"{cod}: devengado supera el comprometido")

        # 5. Una direccion sin codificado casi siempre es un XLS truncado
        if t["codificado"] <= TOL and len(d["partidas"]) == 0:
            errores.append(f"{cod}: sin partidas ni codificado; XLS vacio")

    # 6. El total municipal contra la corrida anterior. Un salto grande
    #    delata direcciones faltantes o un XLS mal leido.
    if previo:
        antes = (previo.get("total") or {}).get("codificado")
        antes_n = previo.get("n_direcciones")
        # Solo se compara contra una corrida al menos tan completa como esta.
        # Si la anterior traia menos direcciones, su total es mas bajo por
        # construccion y la variacion no dice nada.
        comparable = bool(antes_n) and antes_n >= len(direcciones)
        if antes and antes > 0 and comparable:
            var = (total["codificado"] - antes) / antes * 100
            if abs(var) > 5:
                nivel = errores if abs(var) > 15 else alertas
                nivel.append(
                    f"el codificado municipal varia {var:+.2f} % contra la "
                    f"corrida anterior ({antes:,.2f} -> "
                    f"{total['codificado']:,.2f})")
        elif antes and antes > 0:
            alertas.append(
                f"no se compara el total: la corrida anterior traia "
                f"{antes_n} direcciones y esta trae {len(direcciones)}")
        if antes_n and len(direcciones) < antes_n:
            errores.append(
                f"llegaron {len(direcciones)} direcciones, antes habia "
                f"{antes_n}: hay descargas faltantes")

    return errores, alertas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", default="datos")
    ap.add_argument("--forzar", action="store_true",
                    help="escribe el consolidado aunque el cuadre falle")
    ap.add_argument("--salida", default="datos-municipio.json")
    a = ap.parse_args()

    cat = catalogo()
    # Se busca en profundidad: al reunir artefactos, los XLS pueden quedar en
    # datos/ o en datos/datos/. Si el mismo archivo aparece dos veces se
    # conserva uno solo, por nombre.
    rutas, vistos = [], set()
    for r in sorted(glob.glob(os.path.join(a.datos, "**", "partidas_*.xls"),
                              recursive=True)):
        nombre = os.path.basename(r)
        if nombre in vistos:
            continue
        vistos.add(nombre)
        rutas.append(r)
    if not rutas:
        raise SystemExit(f"No hay partidas_*.xls en {a.datos} "
                         f"(se busco tambien en subcarpetas)")

    direcciones, avisos = [], []
    for ruta in rutas:
        cod = codigo_de(ruta)
        try:
            d = LP.leer(ruta)
        except Exception as e:
            avisos.append(f"{os.path.basename(ruta)}: {str(e)[:120]}")
            continue

        t = d.get("total") or {}
        ref = cat.get(cod, {})
        direcciones.append({
            "codigo": cod,
            "nombre": ref.get("nombre", ""),
            "archivo": os.path.basename(ruta),
            "asignacion_poa": ref.get("asignacion"),
            "total": {
                "asignacion": t.get("inicial", 0.0),
                "reformas": t.get("reformas", 0.0),
                "codificado": t.get("codificado", 0.0),
                "certificado": t.get("certificado", 0.0),
                "comprometido": t.get("comprometido", 0.0),
                "devengado": t.get("devengado", 0.0),
                "saldo_certificar": t.get("pend_certificar", 0.0),
                "saldo_devengar": t.get("pend_devengar", 0.0),
            },
            "partidas": [dict(p, subs_codigos=[
                s["codigo"] for s in d.get("subpartidas", [])
                if s.get("padre") == p["codigo"]])
                for p in d.get("partidas", [])],
            "subpartidas": d.get("subpartidas", []),
            "avisos": d.get("avisos", []),
        })

    campos = ("asignacion", "reformas", "codificado", "certificado",
              "comprometido", "devengado")
    total = {k: round(sum(x["total"][k] for x in direcciones), 2) for k in campos}

    bloques, n_det, av_det = cargar_detalle(a.datos)
    avisos += av_det

    # El consolidado de la corrida anterior sirve de referencia de cuadre.
    previo = None
    if os.path.exists(a.salida):
        try:
            with open(a.salida, encoding="utf-8") as f:
                previo = json.load(f)
        except Exception:
            previo = None

    errores, alertas = verificar(direcciones, total, previo)

    salida = {
        "fuente": "eGob — GAD Municipal de Riobamba, Consulta presupuestaria",
        "generado": datetime.now(TZ).isoformat(timespec="seconds"),
        "n_direcciones": len(direcciones),
        "total": total,
        "avisos": avisos,
        "cuadre": {"errores": errores, "alertas": alertas,
                   "ok": not errores},
        "detalle": {"archivos": n_det, "subpartidas": len(bloques)},
        "mensual": mensual(direcciones, bloques) if bloques else [],
        "ventana": indicador_ventana(direcciones, bloques) if bloques else None,
        "direcciones": direcciones,
    }

    destino = a.salida
    if errores and not a.forzar:
        # Se escribe aparte para poder revisarlo sin perder el consolidado
        # bueno que ya esta publicado.
        destino = a.salida.replace(".json", "") + ".rechazado.json"

    with open(destino, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, separators=(",", ":"))

    print(f"{len(direcciones)} direcciones · {destino}")
    print(f"  asignacion  {total['asignacion']:>16,.2f}")
    print(f"  reformas    {total['reformas']:>16,.2f}")
    print(f"  codificado  {total['codificado']:>16,.2f}")
    print(f"  devengado   {total['devengado']:>16,.2f}")
    for d in direcciones:
        n = len(d["partidas"])
        print(f"   {d['codigo']:>10} {n:>4} partidas "
              f"{d['total']['codificado']:>16,.2f}  {d['nombre'][:44]}")
    det = salida["detalle"]
    print(f"  detalle: {det['archivos']} archivo(s) · "
          f"{det['subpartidas']} subpartidas con movimiento")
    v = salida["ventana"]
    if v and v["pct"] is not None:
        print(f"  ventana {v['desde']} a {v['hasta']}: "
              f"{v['num']:,.2f} / {v['den']:,.2f} = {v['pct']:.2f}% "
              f"(umbral {v['umbral']}%)")
    elif not salida["mensual"]:
        print("  sin detalle de movimientos: falta la segunda vuelta de descarga")
    for av in avisos:
        print("  ! " + av)

    print("")
    if errores:
        print(f"CUADRE FALLIDO — {len(errores)} error(es) de codificado:")
        for e in errores:
            print("  X " + e)
        for al in alertas:
            print("  ~ " + al)
        if a.forzar:
            print("")
            print("Se escribio de todos modos por --forzar.")
        else:
            print("")
            print(f"El consolidado quedo en {destino} y no se publica.")
            print("Revise las direcciones senaladas y reintente su descarga.")
            return 2
    else:
        print(f"Cuadre correcto: codificado = asignacion + reformas y las "
              f"partidas suman el total en las {len(direcciones)} direcciones.")
        for al in alertas:
            print("  ~ " + al)
    return 0


if __name__ == "__main__":
    sys.exit(main())
