// ============================================================
// notificaciones.js — Toasts y Modales para el sistema PPP
// Reemplaza todos los alert() y confirm() nativos del navegador
// ============================================================

// ------------------------------------------------------------
// TOAST — Notificaciones flotantes (éxito, error, advertencia)
// Uso: showToast("Mensaje", "success" | "error" | "warning")
// ------------------------------------------------------------
function showToast(mensaje, tipo = "success", duracion = 5500) {
    let contenedor = document.getElementById("toast-contenedor");
    if (!contenedor) {
        contenedor = document.createElement("div");
        contenedor.id = "toast-contenedor";
        document.body.appendChild(contenedor);
    }

    const toast = document.createElement("div");
    toast.className = `toast toast-${tipo}`;

    const iconos = { success: "✔", error: "✖", warning: "⚠" };
    toast.innerHTML = `<span class="toast-icono">${iconos[tipo] || "ℹ"}</span><span>${mensaje}</span>`;

    contenedor.appendChild(toast);

    // Animación de entrada
    setTimeout(() => toast.classList.add("toast-visible"), 20);

    // Animación de salida y eliminación
    setTimeout(() => {
        toast.classList.remove("toast-visible");
        setTimeout(() => toast.remove(), 400);
    }, duracion);
}

// ------------------------------------------------------------
// MODAL — Ventana de confirmación (reemplaza confirm())
// Uso: showModal({ titulo, mensaje, txtConfirmar, txtCancelar, onConfirmar, onCancelar })
// ------------------------------------------------------------
function showModal({ titulo = "Aviso", mensaje = "", txtConfirmar = "Aceptar", txtCancelar = null, onConfirmar = null, onCancelar = null }) {
    // Eliminar modal previo si existe
    const previo = document.getElementById("modal-overlay");
    if (previo) previo.remove();

    const overlay = document.createElement("div");
    overlay.id = "modal-overlay";

    overlay.innerHTML = `
        <div class="modal-caja">
            <div class="modal-titulo">${titulo}</div>
            <div class="modal-mensaje">${mensaje}</div>
            <div class="modal-botones">
                ${txtCancelar ? `<button id="modal-btn-cancelar" class="modal-btn modal-btn-secundario">${txtCancelar}</button>` : ""}
                <button id="modal-btn-confirmar" class="modal-btn modal-btn-principal">${txtConfirmar}</button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);
    setTimeout(() => overlay.classList.add("modal-visible"), 10);

    function cerrarModal() {
        overlay.classList.remove("modal-visible");
        setTimeout(() => overlay.remove(), 300);
    }

    document.getElementById("modal-btn-confirmar").onclick = () => {
        cerrarModal();
        if (onConfirmar) onConfirmar();
    };

    if (txtCancelar) {
        document.getElementById("modal-btn-cancelar").onclick = () => {
            cerrarModal();
            if (onCancelar) onCancelar();
        };
    }
}
