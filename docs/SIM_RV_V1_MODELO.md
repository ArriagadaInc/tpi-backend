# Modelo de cálculo del simulador de renta vitalicia (SIM-RV-V1)

**Estado:** todo lo de este documento se dedujo observando 435 respuestas del portal de Penta Vida
(`PensionMensual/Simular`) con datos ficticios y se validó con campañas ciegas (predicciones congeladas antes de
consultar). **No es la normativa de la CMF/SP ni el código de Penta.** Constantes marcadas *(empírica)* son ajustes que
reproducen el portal, no hechos confirmados. El motor vive en `app/simulador_pension` (módulo puro, sin I/O ni
importaciones del resto de `app`).

Desde `SIM-EVIDENCIA-ENTRADAS` (decisión del humano 2026-10-15), las entradas y el resultado de cada simulación se
guardan como evidencia de solo escritura en `tpi.auditoria.detalle` (append-only, sin nombres, RUT, correo ni teléfono).
La aplicación no lee ese detalle: no es un modelo de persistencia legible ni un historial. La retención es **indefinida**
(decisión del humano 2026-10-19): el detalle se conserva mientras exista `tpi.auditoria`, sin purga ni expiración. Queda
pendiente la revisión normativa de esa decisión (ver `docs/SIM_RV_V1_PENDIENTES.md`, punto 6) y mostrar la evidencia en la
línea de tiempo es `SIM-HISTORIAL-LINEA-TIEMPO`.

## 1. Tiempo, edad y mortalidad (comunes a todo)

* **Tiempo mensual.** Solo importan el mes y el año de la fecha de simulación; el día no influye.
* **Edad en meses** de cada persona: `12·Δaños + Δmeses − [día de nacimiento ≥ 15] + 1` *(empírica: el día ≥ 15 cuenta como mes
  siguiente y se suma 1 mes)*.
* **Tablas** (CMF 2020, `app/simulador_pension/datos/tablas_mortalidad.npz`): causante vejez → CB-H-2020 (hombre) /
  RV-M-2020 (mujer); cónyuge e hijos no inválidos → CB-2020 (hombre) / B-2020 (mujer); hijos inválidos → MI-2020.
* **Mejoramiento continuo:** `q(x, m) = q2020(x) · Π (1 − AA(x, año))` con exponente fraccionario
  `N = (t0 + m)/12 − 2020 + c`, `c = −0,4568` años *(empírica)*, `t0 = año·12 + mes − 1`.
* **Supervivencia mensual** `s[m]` (vivo al comienzo del mes `m`, `s[0] = 1`): muertes uniformes dentro del año de edad
  (UDD), `p_mes = (1 − (μ+1)/12·q) / (1 − μ/12·q)` con `μ` = mes dentro del año de edad.
* **Descuento:** `g = (1+i)^(1/12)`, `j = g − 1`, `i` = tasa de venta anual.

## 2. Renta vitalicia inmediata

Por 1 UF de pensión base `P` del causante:

```
A_causante = Σ_m g^−m · s_c(m)
Q          = 15 · (g − j·A_causante)            deducción por cuota mortuoria (solo del causante)
pago(m)    = b(m) · ( 1            si m < G      periodo garantizado, se paga completo
                      u(m)         si m ≥ G )
b(m)       = 1 + f·[m < T]                      aumento temporal (f = %/100, T meses): multiplica todo el flujo
u(m)       = s_c(m) + (1 − s_c(m))·sob(m)       sob = pensión de sobrevivencia esperada, vidas independientes
A          = Σ_m g^−m · pago(m)
P          = (S − Q) / A         CNU = S·A/(S − Q)      Prima = S      PrimaNetaAfp = 0
```

Sin cónyuge, hijos, garantía ni aumento: `u = s_c` y `A = A_causante`.

### Cónyuge e hijos (`sob`)

| Regla | Valor |
|---|---|
| Cónyuge | 60% de `P`; **50% mientras exista un hijo común con derecho** (el recuento es por edad, no por supervivencia). Un hijo no común no lo baja. Tabla B-2020/CB-2020. |
| Hijo no inválido | 15% de `P`, con derecho hasta los 24 años (edad en meses con la regla de §1). |
| Hijo inválido total | 15%, de por vida, tabla MI-2020. |
| Hijo inválido parcial | 15% hasta los 24 años y 11% desde entonces, de por vida, tabla MI-2020. |
| Sin cónyuge | cada hijo con derecho cobra `pct + 0,50/n`, `n` = hijos con derecho ese mes (recuento determinista por edad, sin tope de 100%). |
| Garantía larga | si `G ≥ 111·12 − edad del causante en meses`, el flujo propio de los hijos se corta en `G` (el del cónyuge no). |

## 3. Renta temporal + renta vitalicia diferida (causante individual)

`N` años de diferimiento (`n = 12N` meses). `P` es la pensión de la RVD y `RT = P/r` la renta temporal mensual, con
`r` = 1 (RVD = 100% de la RT), 0,5, o el % de "Otro RVD" (51–99).

```
Prima  = A_def·P + Q_ins           A_def = Σ_{m≥n} s_m·g^−m        Q_ins = 15·Σ_{m≥n} (s_m − s_{m+1})·g^−m
D      = 12·Σ_{k<N} 1,0367^−k      reserva AFP por unidad de RT: anualidad anticipada anual al 3,67%, sin mortalidad
a_N    = Σ_{k<N} s_{12k}·1,0367^−k
E      = C·f                       C = min(κ·a_N·RT, 60 UF)     κ = 0,2445 (empírica)
                                   f = max(Prima/S, min(1, 3000/S))     (empírica)
S      = Prima + D·RT + E          se resuelve P por bisección;  CNU = Prima/P;  PrimaNetaAfp = S − Prima
```

La parte de la aseguradora (`Prima`) y la reserva `D·RT` coinciden con la fórmula de renta temporal de la Superintendencia de
Pensiones. El término de comisión `E` es el menos entendido: κ, el tope de 60 UF, el prorrateo `f` y el umbral de 3.000 UF son
medidos.

## 4. Precisión medida (435 simulaciones del portal; ver `tests/unit/test_sim_rv_regresion_portal.py`)

| Categoría | Casos | Error máx. en pensión (UF) |
|---|---|---|
| Individual | 63 | 0,12 hasta 96 años; 0,41 a los 99 |
| Cónyuge | 24 | 0,12 |
| Individual o cónyuge con garantía/aumento | 59 | 0,01 |
| Hijos | 153 | 0,04 (0,12 con 2+ hijos inválidos y sin cónyuge) |
| Renta temporal + RVD | 136 | 0,15 |

Total: 435/435 dentro de ±1 UF; 335 exactos a 2 decimales.

## 5. Lo que NO está reconstruido

* **Bono de reconocimiento:** el portal devuelve error de servidor ante cualquier bono > 0 (19 intentos con datos variados).
* Pensiones de invalidez y sobrevivencia como tipo de pensión; padre, madre, conviviente civil, cónyuge inválido, parejas del
  mismo sexo, más de 4 hijos.
* Renta temporal combinada con cónyuge, hijos, garantía o aumento.
* `TotalCuotaMortuoriaUnitaria` (su interpretación quedó pendiente) y la **tasa de venta automática** del portal (viene de un
  catálogo que cambia con el tiempo: 2,63% el 13/10/2026, 2,88% antes).
* Renta temporal con capital entre ~3.000 y ~25.000 UF, diferimiento de 6+ años y `Prima/S` bajo: el error llega a ~0,16 UF.
* Ventana de fechas validada: 15-oct-2025 a 13-oct-2026 (el propio portal solo acepta fechas hasta hoy y hasta un año atrás).
  Desde `SIM-RV-V1-VENTANA` (decisión del humano 2026-10-14) la ventana queda abierta: la simulación se genera para cualquier fecha
  con aviso de valores referenciales; el motor conserva `VENTANA_VALIDADA` y un `warnings.warn` informativo que no llega a pantalla
  ni al PDF. Edades del causante cubiertas: individual 60–100, con cónyuge 60–92, con hijos 62–92, renta temporal 59–88; cónyuge 46–96;
  hijos 0–41; saldo 500–100.000 UF (renta temporal desde 1.000); tasa 0,5–7,5% (8% en renta temporal); garantía hasta 480 meses;
  aumento hasta 600 meses y 100%; diferimiento de 1 a 10 años. Fuera de esos rangos el motor extrapola sin evidencia.
