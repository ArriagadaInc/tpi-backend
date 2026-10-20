# Tablas de mortalidad del simulador

Esta carpeta guarda **de dónde salen** las tablas de mortalidad del simulador de renta vitalicia y **cómo se
regeneran**. El manual completo está en [`docs/SIMULADOR_USO.md`](../../docs/SIMULADOR_USO.md) (§8.2).

| Archivo | Para qué sirve |
|---|---|
| `tablas-mortalidad-cmf.xlsx` | Excel oficial de la CMF («Tablas de Mortalidad Histórica»), conservado sin editar. |
| `procedencia.json` | Fuente, norma, fecha de descarga, tamaño y `sha256` del Excel, y lo ya verificado. |
| `construir_tablas.py` | Lee el Excel y escribe `app/simulador_pension/datos/tablas_mortalidad.npz`. |

## Qué contiene el resultado

`tablas_mortalidad.npz` tiene 12 arreglos, uno por tipo (`vejez`, `sobrev`, `inval`) y sexo (`H`, `M`):

* `<tipo>_<sexo>_q`: probabilidad de muerte `q(edad)` base 2020, edades 0 a 110.
* `<tipo>_<sexo>_aa`: factores de mejoramiento anual `AA(edad, año)`, años 2021 a 2036.

Se usa solo la serie **2020** de cada hoja. Qué tabla usa el simulador en cada rol:

| Rol en el simulador | Hombre | Mujer |
|---|---|---|
| Causante (vejez) | CB-H-2020 | RV-M-2020 |
| Cónyuge e hijos no inválidos | CB-H-2020 | B-M-2020 |
| Hijos inválidos | MI-H-2020 | MI-M-2020 |

Los títulos que trae el Excel en sus hojas son `CB-2020-HOMBRES`, `RV-2020-MUJERES`, `B-2020-MUJERES` y
`MI-2020-HOMBRES/MUJERES`; la norma de la CMF las llama CB-H-2020, RV-M-2020, B-M-2020 y MI-H/M-2020.

## Comandos

Desde la raíz del repositorio:

```bash
# Comprobar que el .npz del motor coincide con el Excel del repo (no escribe nada)
python scripts/tablas_mortalidad/construir_tablas.py --verificar

# Regenerar el .npz desde el Excel del repo
python scripts/tablas_mortalidad/construir_tablas.py

# Regenerar desde un Excel nuevo
python scripts/tablas_mortalidad/construir_tablas.py ruta/al/excel-nuevo.xlsx
```

El script comprueba los encabezados de cada hoja (título de la serie 2020, columnas «Edad» y «qx 2020», y los años 2021 a
2036) antes de leer. Si la CMF reordena el archivo o agrega series, falla con un mensaje claro en vez de leer columnas
equivocadas. Si el Excel no es el registrado en `procedencia.json`, avisa por la salida de error.

## Cuando la CMF publique tablas nuevas

Las tablas 2020 rigen desde el 1-jul-2023 (Norma de Carácter General N.º 495 de la CMF) y, según el sitio oficial, deben
usarse por un máximo de 6 años: revisarlas hacia **mediados de 2029**. Pasos:

1. Descargar el Excel nuevo desde la [página de tablas de la CMF](https://www.cmfchile.cl/portal/principal/623/w4-article-99359.html)
   y contrastarlo con los archivos de la [Superintendencia de Pensiones](https://www.spensiones.cl/portal/institucional/594/w3-article-15658.html).
2. Reemplazar `tablas-mortalidad-cmf.xlsx` y **actualizar `procedencia.json`** (fuente, norma, fecha, bytes y `sha256`):
   `python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" tablas-mortalidad-cmf.xlsx`.
3. Si el Excel nuevo cambia la estructura (otra serie, otras columnas), ajustar `HOJAS`, `SERIE` y las constantes del script.
4. Regenerar el `.npz` y comprobar con `--verificar`.
5. Contrastar con el portal con una campaña ciega de 30 casos o más, regenerar el fixture y correr la regresión.
6. Subir `__version__` en `app/simulador_pension/__init__.py` y actualizar la documentación (ver el manual).

La prueba `tests/unit/test_tablas_mortalidad.py` falla en el CI si el Excel, `procedencia.json` y el `.npz` dejan de
ser coherentes entre sí.

## Procedencia

La copia del Excel viene de la investigación de homologación del simulador (carpeta de trabajo REA, entrega
2026-10-13), descargada de la CMF el 2026-10-13. El script es el de esa investigación
(`REA/simulador_pension/scripts/construir_tablas.py`) con tres cambios: escribe en este repositorio, valida los
encabezados y tiene el modo `--verificar`. Con él, el `.npz` que ya usaba el motor se reconstruye idéntico (los 12 arreglos).
