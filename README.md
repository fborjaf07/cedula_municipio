# Regla de asignacion minima prioritaria (65 % en 2026)

GAD Municipal del Canton Riobamba. Comprobacion propia del cumplimiento de la
regla del articulo 198.1 del COOTAD, con los datos de eGob.

## Por que un repo aparte

El tablero de la cedula de Obras Publicas ya funciona y se regenera solo. Esto
es otro calculo, con otro alcance (las 23 direcciones) y otra periodicidad, asi
que va separado: si la descarga municipal falla, el tablero de Obras Publicas
no se entera.

## Lo que dice la norma

El detalle completo esta en regla-70-30.txt. En resumen:

    % Cumplimiento = Gasto Computable Devengado / Egresos No Financieros Devengados x 100

Para 2026 se mide el devengado del 1 de junio al 30 de noviembre de 2026 y
debe alcanzar al menos el 65 %. Luego 68 % en 2027 y 70 % desde 2028.

eGob no acepta el filtro de fechas en la consulta, asi que la ventana no se
puede pedir al sistema: hay que bajar el detalle de movimientos, que trae la
fecha de cada uno, y filtrar despues.

## Lo que falta

Del repo del tablero hay que copiar dos lectores, tal como estan:

    leer_partida_xls.py
    leer_detalle_xls.py

Y hay que escribir dos archivos nuevos:

    3_regla.py     consolida los 23 XLS y arma datos-regla.json
    regla.html     el tablero con el semaforo del 65 %

## Pasos

    export EGOB_USUARIO=...
    export EGOB_CLAVE=...

1. Cedulas de las 23 direcciones (denominador y numerador codificado):

       python 1_descargar.py --por-direccion --sin-detalle

   Al terminar compara cada direccion con la asignacion del POA. El total
   esperado es 106,871,774.85. Si alguna dice NO CUADRA, repitala antes de
   seguir.

2. Detalle de movimientos (de aqui sale el devengado con fecha):

       python 1_descargar.py --por-direccion --lote

   Es la parte pesada. Conviene hacerla en tandas de cinco o seis direcciones
   y conservar datos/detalle/ entre tandas: es acumulativo.

3. Consolidar y publicar (cuando exista 3_regla.py):

       python 3_regla.py --datos datos --salida datos-regla.json --html regla.html

## Comprobaciones obligatorias

En este orden. Sin las tres, el porcentaje no es defendible:

1. La suma de las 23 asignaciones iniciales contra el POA.
2. El codificado de cada direccion contra su cedula impresa.
3. El devengado del detalle contra el devengado de la cedula. La diferencia
   debe ser exactamente lo devengado fuera de la ventana junio-noviembre.
