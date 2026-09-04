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

TZ = timezone(timedelta(hours=-5))


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
            "partidas": d.get("partidas", []),
            "subpartidas": d.get("subpartidas", []),
            "avisos": d.get("avisos", []),
        })

    campos = ("asignacion", "reformas", "codificado", "certificado",
              "comprometido", "devengado")
    total = {k: round(sum(x["total"][k] for x in direcciones), 2) for k in campos}

    salida = {
        "fuente": "eGob — GAD Municipal de Riobamba, Consulta presupuestaria",
        "generado": datetime.now(TZ).isoformat(timespec="seconds"),
        "n_direcciones": len(direcciones),
        "total": total,
        "avisos": avisos,
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
    for av in avisos:
        print("  ! " + av)


if __name__ == "__main__":
    main()
