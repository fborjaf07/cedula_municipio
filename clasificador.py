#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clasificador.py — Criterio legal de gasto computable y de egresos no
financieros, en un solo sitio.

Base: COOTAD art. 198.1 (denominador) y art. 198.2 (numerador), reformados
por la Ley Organica Reformatoria publicada en el R.O. 6to Suplemento 229 del
23 de febrero de 2026.
"""

# Art. 198.1: egresos no financieros son todos los grupos menos estos.
FUERA_DEL_DENOMINADOR = ("56", "87", "96", "97", "98", "99")

# Art. 198.2: grupos computables completos.
GRUPOS_COMPUTABLES = ("75", "77", "84", "88")

# Art. 198.2 letra a): del 73 solo estos subgrupos.
SUBGRUPOS_73 = ("73.01", "73.02", "73.03", "73.04", "73.05", "73.06",
                "73.08", "73.10", "73.11", "73.14", "73.15", "73.16")

# Art. 198.2 letra a) numeral b: items excluidos dentro del 73.02.
ITEMS_EXCLUIDOS = ("73.02.05", "73.02.21", "73.02.48", "73.02.49")


def en_denominador(codigo):
    """El codigo entra en los egresos no financieros."""
    return str(codigo).strip()[:2] not in FUERA_DEL_DENOMINADOR


def es_computable(codigo):
    """El codigo es gasto computable de inversion.

    No cubre la exclusion cualitativa del art. 9 del Reglamento -el gasto
    que, aun estando en un grupo habilitado, no se vincula a una obra o a un
    servicio efectivo-, que es de criterio y no se puede deducir del codigo.
    """
    c = str(codigo).strip()
    g = c[:2]
    if g in GRUPOS_COMPUTABLES:
        return True
    if g == "73":
        return (c[:5] in SUBGRUPOS_73
                and not any(c.startswith(i) for i in ITEMS_EXCLUIDOS))
    return False
