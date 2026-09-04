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
    rutas = sorted(glob.glob(os.path.join(carpeta, "*.xls")),
                   key=os.path.getmtime)
    for ruta in rutas:
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
                                       **{k: 0.0 for k in campos}})
            r["n"] += 1
            if m["certificado"] < 0 or m["comprometido"] < 0:
                r["anulaciones"] += 1
            for k in campos:
                r[k] += m[k]
            pd = r["por_direccion"].setdefault(dirc, {k: 0.0 for k in campos})
            pg = r["por_grupo"].setdefault(cod[:2], {k: 0.0 for k in campos})
            for k in campos:
                pd[k] += m[k]
                pg[k] += m[k]

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", default="datos")
    ap.add_argument("--salida", default="datos-municipio.json")
    a = ap.parse_args()

    cat = catalogo()
    rutas = sorted(glob.glob(os.path.join(a.datos, "partidas_*.xls")))
    if not rutas:
        raise SystemExit(f"No hay partidas_*.xls en {a.datos}")

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

    bloques, n_det, av_det = cargar_detalle(os.path.join(a.datos, "detalle"))
    avisos += av_det

    salida = {
        "fuente": "eGob — GAD Municipal de Riobamba, Consulta presupuestaria",
        "generado": datetime.now(TZ).isoformat(timespec="seconds"),
        "n_direcciones": len(direcciones),
        "total": total,
        "avisos": avisos,
        "detalle": {"archivos": n_det, "subpartidas": len(bloques)},
        "mensual": mensual(direcciones, bloques) if bloques else [],
        "ventana": indicador_ventana(direcciones, bloques) if bloques else None,
        "direcciones": direcciones,
    }

    with open(a.salida, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, separators=(",", ":"))

    print(f"{len(direcciones)} direcciones · {a.salida}")
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


if __name__ == "__main__":
    main()
