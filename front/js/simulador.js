/* ==========================================================
   SIMULADOR DE RENTA — Tu Pensión Inteligente
   Modelo referencial (no constituye oferta comercial).
   ========================================================== */
(() => {
  'use strict';

  /* ---- Parámetros del modelo (ajustables) ---- */
  const CONFIG = {
    expectativaVida:    90,     // años
    tasaAcumulacion:    0.04,   // rentabilidad real anual en etapa activa
    tasaTecnicaRP:      0.03,   // tasa técnica del retiro programado
    tasaRVBase:         0.038,  // tasa renta vitalicia a los 55 años
    tasaRVIncremento:   0.0009, // incremento por cada año adicional de edad
    ufPorDefecto:       39500   // respaldo si el campo UF queda vacío
  };

  const form = document.getElementById('sim-form');
  if (!form) return;

  const $ = (id) => document.getElementById(id);
  const fmtCLP = new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP', maximumFractionDigits: 0 });
  const fmtUF  = new Intl.NumberFormat('es-CL', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const campos = {
    saldo:      $('sim-saldo'),
    edadActual: $('sim-edad-actual'),
    edadJub:    $('sim-edad-jub'),
    aporte:     $('sim-aporte'),
    uf:         $('sim-uf'),
    modalidad:  form.querySelectorAll('input[name="modalidad"]')
  };

  /* ---- Control de UF manual vs. automática ---- */
  let ufManual = false;
  campos.uf.addEventListener('input', () => { ufManual = true; });

  /* ---- Proyección del saldo hasta la jubilación ---- */
  function saldoProyectado(saldo, aporteMensual, anios) {
    if (anios <= 0) return saldo;
    const g        = Math.pow(1 + CONFIG.tasaAcumulacion, anios);
    const fvAportes = aporteMensual * 12 * ((g - 1) / CONFIG.tasaAcumulacion);
    return saldo * g + fvAportes;
  }

  /* ---- Pensión estimada: Retiro Programado ---- */
  function retiroProgramado(saldo, edadJub) {
    const meses = Math.max((CONFIG.expectativaVida - edadJub) * 12, 12);
    const r     = Math.pow(1 + CONFIG.tasaTecnicaRP, 1 / 12) - 1; // tasa mensual
    return {
      mensual: (saldo * r) / (1 - Math.pow(1 + r, -meses)),
      anios:   meses / 12
    };
  }

  /* ---- Pensión estimada: Renta Vitalicia ---- */
  function rentaVitalicia(saldo, edadJub) {
    const extra = Math.min(Math.max(edadJub - 55, 0), 20);
    const tasa  = CONFIG.tasaRVBase + extra * CONFIG.tasaRVIncremento;
    return { mensual: (saldo * tasa) / 12, tasa };
  }

  /* ---- Plantilla de tarjeta de resultado ---- */
  function tarjeta(titulo, mensual, valorUF, hechos) {
    return `
      <article class="sim-card">
        <h4>${titulo}</h4>
        <p class="sim-card__amount">${fmtCLP.format(mensual)}<span>/mes</span></p>
        <p class="sim-card__uf">≈ ${fmtUF.format(mensual / valorUF)} UF/mes</p>
        <ul>${hechos.map(h => `<li>${h}</li>`).join('')}</ul>
      </article>`;
  }

  /* ---- Cálculo y renderizado ---- */
  function calcular() {
    const saldo      = Number(campos.saldo.value);
    const edadActual = Number(campos.edadActual.value);
    let   edadJub    = Number(campos.edadJub.value);
    const aporte     = Number(campos.aporte.value);
    let   valorUF    = Number(campos.uf.value);
    const modalidad  = [...campos.modalidad].find(r => r.checked).value;

    if (!valorUF || valorUF <= 0) valorUF = CONFIG.ufPorDefecto;

    /* Nunca calcular jubilación antes de la edad actual */
    let aviso = '';
    if (edadJub < edadActual) {
      aviso  = '⚠️ La edad de jubilación ingresada es menor que tu edad actual: calculamos como si te pensionaras hoy.';
      edadJub = edadActual;
    }
    const aniosRestantes = edadJub - edadActual;

    const saldoFuturo = saldoProyectado(saldo, aporte, aniosRestantes);
    const rp          = retiroProgramado(saldoFuturo, edadJub);
    const rv          = rentaVitalicia(saldoFuturo, edadJub);

    /* Resumen */
    $('sim-summary').innerHTML = `
      ${aniosRestantes > 0
        ? `En <strong>${aniosRestantes} ${aniosRestantes === 1 ? 'año' : 'años'}</strong>, tu saldo proyectado sería de`
        : 'Tu saldo estimado al pensionarte es de'}
      <strong>${fmtCLP.format(saldoFuturo)}</strong> (${fmtUF.format(saldoFuturo / valorUF)} UF).
      ${aviso ? `<br>${aviso}` : ''}`;

    /* Tarjetas según modalidad elegida */
    const cards = [];
    if (modalidad !== 'rv') {
      cards.push(tarjeta('Retiro Programado', rp.mensual, valorUF, [
        `Pago estimado por ~${Math.round(rp.anios)} años`,
        'Se recalcula cada año según tu saldo',
        'El saldo restante es heredable'
      ]));
    }
    if (modalidad !== 'rp') {
      cards.push(tarjeta('Renta Vitalicia', rv.mensual, valorUF, [
        'Monto fijo garantizado de por vida',
        'Pensión reajustada según UF',
        'Permite designar beneficiarios'
      ]));
    }
    $('sim-cards').innerHTML = cards.join('');

    /* Etiquetas de los sliders */
    $('out-saldo').textContent      = fmtCLP.format(saldo);
    $('out-edad-actual').textContent = edadActual;
    $('out-edad-jub').textContent   = aviso ? `${edadJub} (hoy)` : edadJub;
    $('out-aporte').textContent     = fmtCLP.format(aporte);

    /* Snapshot de la simulación para el formulario de contacto */
    document.dispatchEvent(new CustomEvent('simulador:change', {
      detail: {
        saldo, edadActual, edadJub, aporte, valorUF,
        saldoFuturo,
        rpMensual: rp.mensual,
        rvMensual: rv.mensual
      }
    }));
  }

  form.addEventListener('input', calcular);
  calcular(); // render inicial

  /* ---- UF automática desde mindicador.cl ---- */
  async function obtenerUF() {
    const status = document.getElementById('uf-status');
    if (!status) return;

    status.textContent = 'Consultando valor UF…';
    try {
      const res = await fetch('https://mindicador.cl/api');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const { uf } = await res.json();

      if (!ufManual && uf?.valor) {
        campos.uf.value = Math.round(uf.valor);
        const fecha = uf.fecha ? new Date(uf.fecha).toLocaleDateString('es-CL') : 'hoy';
        status.textContent = `✓ UF actualizada automáticamente (${fecha})`;
        status.classList.add('ok');
        calcular(); // recalcula con la UF real
      }
    } catch {
      status.textContent = 'No se pudo obtener la UF online; usando el valor manual.';
      status.classList.add('error');
    }
  }

  obtenerUF();

  /* ---- Acceso restringido: revelar simulador interactivo vía hash ---- */
  const simSection = document.getElementById('simulador-interactivo');

  const revelarSimulador = () => {
    if (!simSection) return;
    simSection.hidden = false;
    simSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  // Si se llega desde otra página con el hash (ej. footer del index)
  if (location.hash === '#simulador-interactivo') revelarSimulador();

  // Si se hace click en el botón del footer estando en esta página
  window.addEventListener('hashchange', () => {
    if (location.hash === '#simulador-interactivo') revelarSimulador();
  });
})();
