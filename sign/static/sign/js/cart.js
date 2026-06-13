// Lógica do carrinho de compras (AJAX, sem reload).
// As escritas vão para o backend, que valida o estoque, grava o cookie e
// responde JSON; aqui apenas atualizamos o DOM (badge, modal, subtotais, total).
(function () {
  "use strict";

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  // POST urlencoded com header CSRF; resolve com o JSON da resposta.
  function postCart(url, data) {
    var body = new URLSearchParams(data);
    return fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken(),
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: body.toString(),
    }).then(function (response) {
      return response.json().then(function (json) {
        return { ok: response.ok, data: json };
      });
    });
  }

  // Toast de confirmação (canto inferior direito), some sozinho.
  var toastTimer = null;
  var toastHideTimer = null;
  function showToast(message) {
    var toast = document.getElementById("cart-toast");
    if (!toast) return;
    var msgEl = document.getElementById("cart-toast-message");
    if (msgEl && message) msgEl.textContent = message;
    clearTimeout(toastTimer);
    clearTimeout(toastHideTimer);
    toast.classList.remove("hidden");
    toast.classList.add("flex");
    void toast.offsetWidth; // força reflow para a transição de opacidade valer
    toast.style.opacity = "1";
    toastTimer = setTimeout(function () {
      toast.style.opacity = "0";
      toastHideTimer = setTimeout(function () {
        toast.classList.add("hidden");
        toast.classList.remove("flex");
      }, 300);
    }, 2500);
  }

  // Atualiza o badge de contagem no header.
  function updateBadge(count) {
    var badge = document.getElementById("cart-count");
    if (!badge) return;
    badge.textContent = count;
    badge.classList.toggle("hidden", !count);
  }

  // ----- Modal de adicionar ao carrinho (tela de produtos) -----
  function initAddModal() {
    var modal = document.getElementById("cart-modal");
    if (!modal) return;

    var nameEl = document.getElementById("cart-modal-product");
    var manufacturerEl = document.getElementById("cart-modal-manufacturer");
    var manufacturerCodeEl = document.getElementById("cart-modal-manufacturer-code");
    var barcodeEl = document.getElementById("cart-modal-barcode");
    var maxEl = document.getElementById("cart-modal-max");
    var qtyEl = document.getElementById("cart-modal-quantity");
    var errorEl = document.getElementById("cart-modal-error");
    var confirmBtn = document.getElementById("cart-modal-confirm");
    var cancelBtn = document.getElementById("cart-modal-cancel");
    var addUrl = modal.getAttribute("data-add-url");
    var currentId = null;

    // Mostra "—" quando o valor é vazio (campos opcionais do produto).
    function orDash(value) {
      return value ? value : "—";
    }

    function showError(message) {
      errorEl.textContent = message;
      errorEl.classList.remove("hidden");
    }

    function openModal(button) {
      currentId = button.getAttribute("data-id");
      var max = button.getAttribute("data-max");
      var unit = button.getAttribute("data-unit") || "";
      nameEl.textContent = button.getAttribute("data-name");
      manufacturerEl.textContent = orDash(button.getAttribute("data-manufacturer"));
      manufacturerCodeEl.textContent = orDash(button.getAttribute("data-manufacturer-code"));
      barcodeEl.textContent = orDash(button.getAttribute("data-barcode"));
      maxEl.textContent = (max + " " + unit).trim();
      qtyEl.max = max;
      qtyEl.value = "1";
      errorEl.classList.add("hidden");
      modal.classList.remove("hidden");
      modal.classList.add("flex");
      qtyEl.focus();
    }

    function closeModal() {
      modal.classList.add("hidden");
      modal.classList.remove("flex");
      currentId = null;
    }

    function submit() {
      errorEl.classList.add("hidden");
      postCart(addUrl, { product_id: currentId, quantity: qtyEl.value })
        .then(function (res) {
          if (res.ok && res.data.ok) {
            updateBadge(res.data.cart_count);
            closeModal();
            showToast("Produto adicionado ao carrinho.");
          } else {
            showError(res.data.error || "Não foi possível adicionar.");
          }
        })
        .catch(function () {
          showError("Erro de comunicação. Tente novamente.");
        });
    }

    document.querySelectorAll(".cart-add-btn").forEach(function (button) {
      button.addEventListener("click", function () {
        openModal(button);
      });
    });

    confirmBtn.addEventListener("click", submit);
    cancelBtn.addEventListener("click", closeModal);
    qtyEl.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        submit();
      }
    });
    modal.addEventListener("click", function (event) {
      if (event.target === modal) closeModal();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !modal.classList.contains("hidden")) {
        closeModal();
      }
    });
  }

  // ----- Tela do carrinho (atualizar / remover) -----
  function initCartPage() {
    var app = document.getElementById("cart-app");
    if (!app) return;

    var updateUrl = app.getAttribute("data-update-url");
    var removeUrl = app.getAttribute("data-remove-url");
    var grandTotalEl = document.getElementById("cart-grand-total");

    function setRowError(row, message) {
      var errorEl = row.querySelector(".cart-row-error");
      if (!errorEl) return;
      if (message) {
        errorEl.textContent = message;
        errorEl.classList.remove("hidden");
      } else {
        errorEl.classList.add("hidden");
      }
    }

    function refreshEmptyState() {
      var remaining = app.querySelectorAll("tr[data-id]").length;
      if (remaining === 0) {
        var table = document.getElementById("cart-table-wrap");
        var empty = document.getElementById("cart-empty");
        if (table) table.classList.add("hidden");
        if (empty) empty.classList.remove("hidden");
      }
    }

    app.querySelectorAll(".cart-update-btn").forEach(function (button) {
      button.addEventListener("click", function () {
        var row = button.closest("tr[data-id]");
        var id = row.getAttribute("data-id");
        var input = row.querySelector(".cart-qty-input");
        setRowError(row, "");
        postCart(updateUrl, { product_id: id, quantity: input.value })
          .then(function (res) {
            if (res.ok && res.data.ok) {
              var totalEl = row.querySelector(".cart-item-total");
              if (totalEl) totalEl.textContent = "R$ " + res.data.item_total;
              grandTotalEl.textContent = "R$ " + res.data.grand_total;
              updateBadge(res.data.cart_count);
              showToast("Quantidade atualizada.");
            } else {
              setRowError(row, res.data.error || "Não foi possível atualizar.");
            }
          })
          .catch(function () {
            setRowError(row, "Erro de comunicação. Tente novamente.");
          });
      });
    });

    app.querySelectorAll(".cart-remove-btn").forEach(function (button) {
      button.addEventListener("click", function () {
        var row = button.closest("tr[data-id]");
        var id = row.getAttribute("data-id");
        postCart(removeUrl, { product_id: id })
          .then(function (res) {
            if (res.ok && res.data.ok) {
              row.remove();
              grandTotalEl.textContent = "R$ " + res.data.grand_total;
              updateBadge(res.data.cart_count);
              refreshEmptyState();
              showToast("Item removido do carrinho.");
            } else {
              setRowError(row, res.data.error || "Não foi possível remover.");
            }
          })
          .catch(function () {
            setRowError(row, "Erro de comunicação. Tente novamente.");
          });
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initAddModal();
    initCartPage();
  });
})();
