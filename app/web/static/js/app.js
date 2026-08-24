function showToast(message) {
  const container = document.getElementById("toast-container");
  if (!container) {
    return;
  }

  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = message;
  container.appendChild(toast);

  window.setTimeout(() => {
    toast.remove();
  }, 2600);
}

document.addEventListener("click", (event) => {
  const openDeleteModal = event.target.closest("[data-open-delete-modal]");
  if (openDeleteModal) {
    const modal = document.getElementById("delete-modal");
    if (modal) {
      modal.hidden = false;
    }
    return;
  }

  const closeDeleteModal = event.target.closest("[data-close-delete-modal]");
  if (closeDeleteModal) {
    const modal = document.getElementById("delete-modal");
    if (modal) {
      modal.hidden = true;
    }
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    const modal = document.getElementById("delete-modal");
    if (modal) {
      modal.hidden = true;
    }
  }
});

document.addEventListener("htmx:responseError", () => {
  showToast("No se pudo actualizar la vista de leads");
});
