/* Public lead form: validates for UX and delegates authoritative validation to /api/v1/leads. */
(() => {
  'use strict';

  const form = document.getElementById('lead-form');
  if (!form) return;

  const $ = (id) => document.getElementById(id);
  const status = $('lead-status');
  const submitButton = form.querySelector('button[type="submit"]');
  const fmtInt = new Intl.NumberFormat('es-CL');
  let requestKey = null;
  let simSnapshot = null;
  const simSection = document.getElementById('simulador-interactivo');

  const showStatus = (message, type = '') => {
    status.textContent = message;
    status.className = `lead-status ${type}`.trim();
  };

  const populateSelect = (id, items, placeholder) => {
    const select = $(id);
    select.replaceChildren(new Option(placeholder, ''));
    items.forEach((item) => select.add(new Option(item.nombre, item.id)));
    select.disabled = false;
  };

  const loadCatalogs = async () => {
    try {
      const response = await fetch('/api/v1/catalogs', { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('catalogs_unavailable');
      const catalogs = await response.json();
      populateSelect('lead-genero', catalogs.generos, 'Selecciona tu genero');
      populateSelect('lead-civil', catalogs.estados_civiles, 'Selecciona tu estado civil');
      populateSelect('lead-afp', catalogs.afps, 'Selecciona tu AFP');
    } catch (_) {
      showStatus('El formulario no esta disponible en este momento. Intenta nuevamente mas tarde.', 'error');
    }
  };

  document.addEventListener('simulador:change', (event) => {
    simSnapshot = event.detail;
    const saldo = $('lead-saldo');
    if (simSection && !simSection.hidden && saldo && document.activeElement !== saldo) {
      saldo.value = fmtInt.format(event.detail.saldo);
    }
  });

  const rutInput = $('lead-rut');
  const cleanRut = (value) => value.replace(/[^0-9kK]/g, '').toUpperCase();
  const formatRut = (value) => {
    const clean = cleanRut(value);
    if (clean.length < 2) return clean;
    return clean.slice(0, -1).replace(/\B(?=(\d{3})+(?!\d))/g, '.') + '-' + clean.slice(-1);
  };
  const validRut = (value) => {
    const clean = cleanRut(value);
    if (clean.length < 8) return false;
    const body = clean.slice(0, -1);
    const verifier = clean.slice(-1);
    let sum = 0;
    let multiplier = 2;
    for (let index = body.length - 1; index >= 0; index -= 1) {
      sum += Number(body[index]) * multiplier;
      multiplier = multiplier === 7 ? 2 : multiplier + 1;
    }
    const remainder = 11 - (sum % 11);
    const expected = remainder === 11 ? '0' : remainder === 10 ? 'K' : String(remainder);
    return expected === verifier;
  };

  rutInput.addEventListener('input', () => {
    rutInput.value = formatRut(rutInput.value);
  });

  const saldoInput = $('lead-saldo');
  saldoInput.addEventListener('input', () => {
    const digits = saldoInput.value.replace(/\D/g, '');
    saldoInput.value = digits ? fmtInt.format(Number(digits)) : '';
  });

  $('lead-nacimiento').max = new Date().toISOString().split('T')[0];

  const markInvalid = (element, invalid) => {
    element.closest('.lead-field')?.classList.toggle('invalid', invalid);
    return !invalid;
  };

  const validateForUser = () => {
    let valid = true;
    valid = markInvalid($('lead-nombre'), $('lead-nombre').value.trim().length < 3) && valid;
    valid = markInvalid(rutInput, !validRut(rutInput.value)) && valid;
    valid = markInvalid($('lead-email'), !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test($('lead-email').value.trim())) && valid;
    valid = markInvalid($('lead-telefono'), $('lead-telefono').value.replace(/\D/g, '').length < 8) && valid;
    valid = markInvalid($('lead-nacimiento'), !$('lead-nacimiento').value) && valid;
    valid = markInvalid($('lead-genero'), !$('lead-genero').value) && valid;
    valid = markInvalid($('lead-civil'), !$('lead-civil').value) && valid;
    valid = markInvalid($('lead-afp'), !$('lead-afp').value) && valid;
    valid = markInvalid(saldoInput, !saldoInput.value.replace(/\D/g, '')) && valid;
    const consented = ['lead-terminos', 'lead-privacidad', 'lead-contacto'].every((id) => $(id).checked);
    if (!valid || !consented) {
      showStatus('Revisa los campos obligatorios y los tres consentimientos.', 'error');
      return false;
    }
    return true;
  };

  const buildPayload = () => ({
    schema_version: '1.0',
    nombre_completo: $('lead-nombre').value.trim(),
    rut: rutInput.value,
    email: $('lead-email').value.trim(),
    telefono: $('lead-telefono').value.trim(),
    fecha_nacimiento: $('lead-nacimiento').value,
    genero_id: $('lead-genero').value,
    estado_civil_id: $('lead-civil').value,
    afp_id: $('lead-afp').value,
    saldo_afp: saldoInput.value.replace(/\D/g, ''),
    comentarios: $('lead-mensaje').value.trim() || null,
    consentimientos: {
      acepta_terminos: $('lead-terminos').checked,
      acepta_politica_privacidad: $('lead-privacidad').checked,
      finalidad_contacto: $('lead-contacto').checked,
    },
    honeypot: form.querySelector('[data-honeypot]')?.value || '',
  });

  form.addEventListener('input', () => {
    if (status.classList.contains('error')) showStatus('');
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!validateForUser()) return;

    requestKey = requestKey || crypto.randomUUID();
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 10000);
    submitButton.disabled = true;
    showStatus('Enviando solicitud...');
    try {
      const response = await fetch('/api/v1/leads', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': requestKey,
        },
        body: JSON.stringify(buildPayload()),
        signal: controller.signal,
      });
      if (!response.ok) {
        if (response.status === 400 || response.status === 409 || response.status === 422) requestKey = null;
        throw new Error('lead_rejected');
      }
      await response.json();
      showStatus('Solicitud enviada correctamente. Un asesor te contactara a la brevedad.', 'ok');
      form.reset();
      requestKey = null;
      simSnapshot = null;
    } catch (_) {
      showStatus('No fue posible enviar la solicitud. Intenta nuevamente.', 'error');
    } finally {
      window.clearTimeout(timeout);
      submitButton.disabled = false;
    }
  });

  loadCatalogs();
})();
