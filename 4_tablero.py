#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
4_tablero.py — Convierte datos-municipio.json en datos-regla.json.

Es la transformacion que consume el tablero: aplica el criterio legal a cada
partida y agrega por grupo, por direccion y por mes. Va aparte de
3_convertir.py a proposito: ese solo pasa los XLS a JSON sin interpretar
nada, y asi la conversion se puede revisar sin discutir el criterio.

Uso:
    python3 4_tablero.py --entrada datos-municipio.json --salida datos-regla.json
"""

import argparse
import json
from datetime import datetime, timezone, timedelta

from clasificador import es_computable, en_denominador

TZ = timezone(timedelta(hours=-5))

NOMBRE_GRUPO = {
    "51": "Gastos en personal",
    "53": "Bienes y servicios de consumo",
    "56": "Egresos financieros",
    "57": "Otros gastos corrientes",
    "58": "Transferencias corrientes",
    "71": "Gastos en personal para inversion",
    "73": "Bienes y servicios para inversion",
    "75": "Obras publicas",
    "77": "Otros egresos de inversion",
    "78": "Transferencias de inversion",
    "84": "Bienes de larga duracion",
    "87": "Inversiones financieras",
    "88": "Transferencias o donaciones de capital",
    "96": "Amortizacion de la deuda",
    "97": "Pasivo circulante",
    "99": "Otros pasivos",
}

CAMPOS = ("asignacion", "reformas", "codificado", "certificado",
          "comprometido", "devengado")


def r2(n):
    return round(float(n or 0), 2)


def construir(M):
    grupos, dirs = {}, []
    num_c = den_c = num_d = den_d = fuera = 0.0

    for x in M["direcciones"]:
        dc = nc = dd = nd = 0.0
        det = {}
        for p in x["partidas"]:
            g = str(p["codigo"])[:2]
            o = grupos.setdefault(g, {"grupo": g, "nombre": NOMBRE_GRUPO.get(g, ""),
                                      "cod": 0.0, "comp": 0.0, "dev": 0.0,
                                      "n": 0, "fuera": not en_denominador(p["codigo"])})
            o["cod"] += p["codificado"]
            o["dev"] += p["devengado"]
            o["n"] += 1
            comp = es_computable(p["codigo"])
            if comp:
                o["comp"] += p["codificado"]

            if not en_denominador(p["codigo"]):
                fuera += p["codificado"]
                continue

            dc += p["codificado"]
            dd += p["devengado"]
            if comp:
                nc += p["codificado"]
                nd += p["devengado"]

            e = det.setdefault(g, {"grupo": g, "nombre": NOMBRE_GRUPO.get(g, ""),
                                   "cod": 0.0, "comp": 0.0, "dev": 0.0})
            e["cod"] += p["codificado"]
            e["dev"] += p["devengado"]
            if comp:
                e["comp"] += p["codificado"]

        num_c += nc
        den_c += dc
        num_d += nd
        den_d += dd
        dirs.append({
            "codigo": x["codigo"], "nombre": x.get("nombre", ""),
            "base": r2(dc), "comp": r2(nc), "dev": r2(dd), "devComp": r2(nd),
            "pct": round(nc / dc * 100, 2) if dc > 0 else None,
            "grupos": [{k: (r2(v) if isinstance(v, float) else v)
                        for k, v in e.items()}
                       for e in sorted(det.values(), key=lambda e: -e["cod"])],
        })

    dirs.sort(key=lambda r: -r["base"])
    G = [{k: (r2(v) if isinstance(v, float) else v) for k, v in o.items()}
         for o in sorted(grupos.values(), key=lambda o: o["grupo"])]

    t = M["total"]
    salida = {
        "fuente": M.get("fuente", ""),
        "generado": datetime.now(TZ).isoformat(timespec="seconds"),
        "corte": datetime.now(TZ).strftime("%d/%m/%Y"),
        "umbral": 65, "ejercicio": 2026,
        "municipio": {k: r2(t.get(k)) for k in CAMPOS},
        "codificado": {"num": r2(num_c), "den": r2(den_c),
                       "pct": round(num_c / den_c * 100, 2) if den_c else None,
                       "brecha": r2(den_c * 0.65 - num_c)},
        "devengado": {"num": r2(num_d), "den": r2(den_d),
                      "pct": round(num_d / den_d * 100, 2) if den_d else None},
        "excluido": r2(fuera),
        "grupos": G,
        "direcciones": dirs,
        "detalle": M.get("detalle"),
        "ventana": M.get("ventana"),
        "nombres": {x["codigo"]: x.get("nombre", "") for x in M["direcciones"]},
        "mensual": [{
            "mes": m["mes"], "etiqueta": m["etiqueta"], "corto": m["corto"],
            "en_ventana": m.get("en_ventana", False),
            "movimientos": m["movimientos"], "anulaciones": m["anulaciones"],
            "certificado": r2(m["certificado"]),
            "comprometido": r2(m["comprometido"]),
            "devengado": r2(m["devengado"]), "pagado": r2(m["pagado"]),
            "acum_devengado": r2(m.get("acum_devengado")),
            "acum_pagado": r2(m.get("acum_pagado")),
            "por_direccion": m.get("por_direccion", {}),
        } for m in M.get("mensual", [])],
        # La cedula completa, para la pestaña que filtra por direccion.
        "cedula": [{
            "codigo": x["codigo"], "nombre": x.get("nombre", ""),
            "total": {k: r2(x["total"].get(k)) for k in CAMPOS},
            "partidas": [{
                "codigo": p["codigo"], "nombre": p["nombre"],
                "computable": es_computable(p["codigo"]),
                "enDenominador": en_denominador(p["codigo"]),
                "asignacion": r2(p["inicial"]), "reformas": r2(p["reformas"]),
                "codificado": r2(p["codificado"]),
                "certificado": r2(p["certificado"]),
                "comprometido": r2(p["comprometido"]),
                "devengado": r2(p["devengado"]),
                "ejecutado": r2(p.get("ejecutado")),
                "subs": [{"codigo": s["codigo"], "nombre": s["nombre"],
                          "codificado": r2(s["codificado"]),
                          "certificado": r2(s["certificado"]),
                          "comprometido": r2(s["comprometido"]),
                          "devengado": r2(s["devengado"])}
                         for s in x.get("subpartidas", [])
                         if s.get("padre") == p["codigo"]],
            } for p in x["partidas"]],
        } for x in M["direcciones"]],
    }
    return salida


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="datos-municipio.json")
    ap.add_argument("--salida", default="datos-regla.json")
    a = ap.parse_args()

    with open(a.entrada, encoding="utf-8") as f:
        M = json.load(f)
    d = construir(M)

    with open(a.salida, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"))

    c, v, w = d["codificado"], d["devengado"], d["ventana"]
    print(f"{len(d['direcciones'])} direcciones -> {a.salida}")
    print(f"  codificado  {c['num']:,.2f} / {c['den']:,.2f} = {c['pct']}%")
    print(f"  devengado   {v['num']:,.2f} / {v['den']:,.2f} = {v['pct']}%")
    if w and w.get("pct") is not None:
        print(f"  ventana {w['desde']} a {w['hasta']}: "
              f"{w['num']:,.2f} / {w['den']:,.2f} = {w['pct']}% (umbral 65%)")
    print(f"  {len(d['mensual'])} meses · {d['excluido']:,.2f} fuera del denominador")


if __name__ == "__main__":
    main()
