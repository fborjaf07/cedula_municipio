"""Direcciones esperadas que no dejaron XLS en datos/.

Imprime los codigos faltantes separados por espacio, o nada si estan todas.
Lo usan los workflows para avisar que hay que reintentar y para decidir si
publican el JSON consolidado.
"""
import json
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).parent
datos = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "datos")

esperadas = [d["codigo"] for d in json.loads(
    (RAIZ / "direcciones.json").read_text(encoding="utf-8"))]

hay = set()
for f in datos.glob("partidas_*.xls"):
    m = re.search(r"partidas_(.+)\.xls$", f.name)
    if m:
        hay.add(m.group(1).replace("_", "."))

faltan = [c for c in esperadas if c not in hay]
print(" ".join(faltan))
