/* Asistente del simulador de pensión (SIM-WIZARD-3-PASOS).

   JavaScript propio, sin dependencias. Gestiona la tabla del grupo familiar (paso 2) y el modal
   de beneficiarios. Los datos viven en los inputs ocultos del formulario (conyuge_*, hijo_*_*),
   que son la única fuente de verdad del DOM; el servidor valida y calcula todo lo demás.
*/
(function () {
  "use strict";

  const form = document.querySelector("form.wizard-form");
  if (!form) {
    return;
  }

  const fechaSimulacion = form.dataset.fechaSimulacion;

  const SEXO_LABEL = { H: "Masculino", M: "Femenino" };
  const INVALIDEZ_LABEL = { no: "No inválido", parcial: "Inválido parcial", total: "Inválido total" };

  const modal = document.getElementById("beneficiario-modal");
  const modalTitulo = document.getElementById("beneficiario-modal-title");
  const modalBotonGuardar = document.getElementById("btn-modal-guardar");
  const modalError = document.getElementById("modal-error");

  const campo = {
    parentesco: document.getElementById("modal-parentesco"),
    relacion: document.getElementById("modal-relacion"),
    relacionField: document.getElementById("modal-relacion-field"),
    sexo: document.getElementById("modal-sexo"),
    invalidez: document.getElementById("modal-invalidez"),
    nacimiento: document.getElementById("modal-nacimiento"),
    edad: document.getElementById("modal-edad"),
  };

  function hijoInputs(i) {
    return {
      sexo: document.getElementById("hijo_sexo_" + i),
      nacimiento: document.getElementById("hijo_nacimiento_" + i),
      comun: document.getElementById("hijo_comun_" + i),
      invalidez: document.getElementById("hijo_invalidez_" + i),
    };
  }

  function leerConyuge() {
    const sexo = (document.getElementById("conyuge_sexo").value || "").trim();
    const nacimiento = (document.getElementById("conyuge_nacimiento").value || "").trim();
    if (!sexo && !nacimiento) {
      return null;
    }
    return {
      sexo: sexo || "H",
      nacimiento: nacimiento,
      invalidez: document.getElementById("conyuge_invalidez").value || "no",
    };
  }

  function leerHijos() {
    const hijos = [];
    for (let i = 1; i <= 4; i++) {
      const inputs = hijoInputs(i);
      const sexo = (inputs.sexo.value || "").trim();
      const nacimiento = (inputs.nacimiento.value || "").trim();
      if (!sexo && !nacimiento) {
        continue;
      }
      hijos.push({
        index: i,
        sexo: sexo || "H",
        nacimiento: nacimiento,
        comun: inputs.comun.value === "1",
        invalidez: inputs.invalidez.value || "no",
      });
    }
    return hijos;
  }

  /* Edad consistente con app/simulador_pension/mortalidad.py::edad_en_meses (meses // 12). */
  function edadEnAnios(nacimientoISO, referenciaISO) {
    const nac = new Date(nacimientoISO + "T00:00:00");
    const ref = new Date(referenciaISO + "T00:00:00");
    if (Number.isNaN(nac.getTime()) || Number.isNaN(ref.getTime())) {
      return null;
    }
    const meses =
      12 * (ref.getFullYear() - nac.getFullYear()) + (ref.getMonth() - nac.getMonth());
    const edadMeses = meses - (nac.getDate() >= 15 ? 1 : 0) + 1;
    return Math.floor(edadMeses / 12);
  }

  function formatearFecha(iso) {
    if (!iso) {
      return "";
    }
    const partes = iso.split("-");
    if (partes.length !== 3) {
      return iso;
    }
    return partes[2] + "/" + partes[1] + "/" + partes[0];
  }

  function celda(texto) {
    const td = document.createElement("td");
    td.textContent = texto;
    return td;
  }

  function botonAccion(texto, etiqueta, onClick, peligro) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "sim-row-action" + (peligro ? " sim-row-action-danger" : "");
    btn.setAttribute("aria-label", etiqueta);
    btn.textContent = texto;
    btn.addEventListener("click", onClick);
    return btn;
  }

  function filaBeneficiario(b, numero) {
    const tr = document.createElement("tr");
    tr.dataset.tipo = b.tipo;
    if (b.tipo === "hijo") {
      tr.dataset.index = String(b.index);
    }

    const nacimientoLabel = formatearFecha(b.nacimiento);
    const edad = edadEnAnios(b.nacimiento, fechaSimulacion);

    tr.appendChild(celda(b.tipo === "conyuge" ? "Cónyuge" : "Hijo/a"));
    tr.appendChild(celda(nacimientoLabel));
    tr.appendChild(celda(SEXO_LABEL[b.sexo] || ""));
    tr.appendChild(celda(INVALIDEZ_LABEL[b.invalidez] || ""));
    tr.appendChild(celda(b.tipo === "hijo" ? (b.comun ? "Común" : "No común") : "—"));
    tr.appendChild(celda(edad === null ? "" : String(edad)));

    const acciones = document.createElement("td");
    acciones.className = "sim-row-actions";
    acciones.appendChild(
      botonAccion("Editar", "Editar beneficiario", () => abrirEditar(b.tipo, b.index), false)
    );
    acciones.appendChild(
      botonAccion("Quitar", "Quitar beneficiario", () => borrar(b.tipo, b.index), true)
    );
    tr.appendChild(acciones);

    return tr;
  }

  function render() {
    const tbody = document.getElementById("familia-beneficiarios");
    tbody.innerHTML = "";

    const conyuge = leerConyuge();
    const hijos = leerHijos();
    let numero = 2; // la fila 1 es el causante

    if (conyuge) {
      tbody.appendChild(filaBeneficiario({ tipo: "conyuge", ...conyuge }, numero++));
    }
    hijos.forEach((hijo) => {
      tbody.appendChild(filaBeneficiario({ tipo: "hijo", ...hijo }, numero++));
    });

    const empty = document.getElementById("familia-empty");
    if (empty) {
      empty.hidden = conyuge !== null || hijos.length > 0;
    }

    const btnAgregar = document.getElementById("btn-agregar-beneficiario");
    if (btnAgregar) {
      btnAgregar.disabled = conyuge !== null && hijos.length >= 4;
    }
  }

  /* ---------------- Modal ---------------- */

  let editando = null; // null | { tipo: "conyuge" } | { tipo: "hijo", index }

  function sincronizarOpcionesParentesco() {
    const conyuge = leerConyuge();
    const hijos = leerHijos();
    for (const option of campo.parentesco.options) {
      if (option.value === "conyuge") {
        option.disabled = conyuge !== null;
      } else if (option.value === "hijo") {
        option.disabled = hijos.length >= 4;
      }
    }
  }

  function sincronizarRelacion() {
    const esConyuge = campo.parentesco.value === "conyuge";
    campo.relacion.disabled = esConyuge;
    if (campo.relacionField) {
      campo.relacionField.classList.toggle("is-disabled", esConyuge);
    }
  }

  function actualizarEdad() {
    const valor = campo.nacimiento.value;
    if (!valor) {
      campo.edad.value = "";
      return;
    }
    const edad = edadEnAnios(valor, fechaSimulacion);
    campo.edad.value = edad === null ? "" : String(edad);
  }

  function mostrarError(mensaje) {
    if (!mensaje) {
      modalError.hidden = true;
      modalError.textContent = "";
      return;
    }
    modalError.hidden = false;
    modalError.textContent = mensaje;
  }

  function abrirModal() {
    modal.hidden = false;
    setTimeout(() => campo.parentesco.focus(), 0);
  }

  function cerrarModal() {
    modal.hidden = true;
    editando = null;
    mostrarError("");
  }

  function abrirAgregar() {
    editando = null;
    campo.parentesco.disabled = false;
    sincronizarOpcionesParentesco();
    campo.parentesco.value = campo.parentesco.options[0].disabled ? "hijo" : campo.parentesco.options[0].value;
    // Preferir "hijo/a" por defecto salvo que ya haya 4 hijos.
    if (!campo.parentesco.querySelector('option[value="hijo"]').disabled) {
      campo.parentesco.value = "hijo";
    }
    campo.relacion.value = "no-comun";
    campo.sexo.value = "H";
    campo.invalidez.value = "no";
    campo.nacimiento.value = "";
    campo.edad.value = "";
    sincronizarRelacion();
    modalTitulo.textContent = "Agregar beneficiario";
    modalBotonGuardar.textContent = "Agregar";
    mostrarError("");
    abrirModal();
  }

  function abrirEditar(tipo, index) {
    if (tipo === "conyuge") {
      const conyuge = leerConyuge();
      if (!conyuge) {
        return;
      }
      editando = { tipo: "conyuge" };
      campo.parentesco.value = "conyuge";
      campo.relacion.value = "no-comun";
      campo.sexo.value = conyuge.sexo;
      campo.invalidez.value = conyuge.invalidez;
      campo.nacimiento.value = conyuge.nacimiento;
    } else {
      const inputs = hijoInputs(index);
      if (!inputs.sexo) {
        return;
      }
      editando = { tipo: "hijo", index: index };
      campo.parentesco.value = "hijo";
      campo.relacion.value = inputs.comun.value === "1" ? "comun" : "no-comun";
      campo.sexo.value = inputs.sexo.value || "H";
      campo.invalidez.value = inputs.invalidez.value || "no";
      campo.nacimiento.value = inputs.nacimiento.value || "";
    }

    campo.parentesco.disabled = true;
    actualizarEdad();
    sincronizarRelacion();
    modalTitulo.textContent = "Editar beneficiario";
    modalBotonGuardar.textContent = "Guardar";
    mostrarError("");
    abrirModal();
  }

  function guardar() {
    const tipo = campo.parentesco.value;
    const nacimiento = campo.nacimiento.value;

    if (!nacimiento) {
      mostrarError("Debes ingresar la fecha de nacimiento.");
      return;
    }
    if (tipo === "conyuge" && campo.invalidez.value !== "no") {
      mostrarError("Un cónyuge inválido no es un escenario soportado por el simulador.");
      return;
    }

    const comun = campo.relacion.value === "comun";

    if (editando && editando.tipo === "hijo") {
      const inputs = hijoInputs(editando.index);
      inputs.sexo.value = campo.sexo.value;
      inputs.nacimiento.value = nacimiento;
      inputs.comun.value = comun ? "1" : "";
      inputs.invalidez.value = campo.invalidez.value;
    } else if (editando && editando.tipo === "conyuge") {
      document.getElementById("conyuge_sexo").value = campo.sexo.value;
      document.getElementById("conyuge_nacimiento").value = nacimiento;
      document.getElementById("conyuge_invalidez").value = campo.invalidez.value;
    } else if (tipo === "conyuge") {
      document.getElementById("conyuge_sexo").value = campo.sexo.value;
      document.getElementById("conyuge_nacimiento").value = nacimiento;
      document.getElementById("conyuge_invalidez").value = campo.invalidez.value;
    } else {
      // nuevo hijo: usar el primer índice libre 1..4
      const hijos = leerHijos();
      const ocupados = new Set(hijos.map((h) => h.index));
      let libre = 0;
      for (let i = 1; i <= 4; i++) {
        if (!ocupados.has(i)) {
          libre = i;
          break;
        }
      }
      if (!libre) {
        mostrarError("Ya alcanzaste el máximo de 4 hijos.");
        return;
      }
      const inputs = hijoInputs(libre);
      inputs.sexo.value = campo.sexo.value;
      inputs.nacimiento.value = nacimiento;
      inputs.comun.value = comun ? "1" : "";
      inputs.invalidez.value = campo.invalidez.value;
    }

    render();
    cerrarModal();
  }

  function borrar(tipo, index) {
    if (tipo === "conyuge") {
      document.getElementById("conyuge_sexo").value = "";
      document.getElementById("conyuge_nacimiento").value = "";
      document.getElementById("conyuge_invalidez").value = "no";
    } else {
      const inputs = hijoInputs(index);
      inputs.sexo.value = "";
      inputs.nacimiento.value = "";
      inputs.comun.value = "";
      inputs.invalidez.value = "no";
    }
    render();
  }

  /* ---------------- Wiring ---------------- */

  document.getElementById("btn-agregar-beneficiario").addEventListener("click", abrirAgregar);
  document.getElementById("btn-modal-cancelar").addEventListener("click", cerrarModal);
  document.getElementById("btn-modal-cerrar").addEventListener("click", cerrarModal);
  document.getElementById("btn-modal-guardar").addEventListener("click", guardar);

  campo.parentesco.addEventListener("change", () => {
    sincronizarRelacion();
    mostrarError("");
  });
  campo.nacimiento.addEventListener("input", actualizarEdad);
  campo.invalidez.addEventListener("change", () => mostrarError(""));

  modal.addEventListener("click", (event) => {
    if (event.target === modal) {
      cerrarModal();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) {
      cerrarModal();
    }
  });

  render();

  /* En pantallas angostas el resultado queda debajo del formulario: se lleva a la vista. */
  const resultado = document.getElementById("resultado");
  if (resultado && resultado.dataset.hasResult && window.matchMedia("(max-width: 1100px)").matches) {
    resultado.scrollIntoView({ block: "start" });
  }
})();
