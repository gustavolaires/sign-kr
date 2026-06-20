// Tela de checkout: linhas de pagamento dinâmicas, alternância de desconto e
// recálculo ao vivo do resumo (subtotal/desconto/total/pago/troco).
// O cálculo aqui é só para exibição — o backend (sign.services.create_sale) é
// a fonte autoritativa e revalida tudo em centavos.
(function () {
  "use strict";

  var CREDIT = "credit";

  var app = document.getElementById("checkout-app");
  if (!app) return;

  var subtotalCents = parseInt(app.getAttribute("data-subtotal-cents"), 10) || 0;

  var modeEl = document.getElementById("discount-mode");
  var amountEl = document.getElementById("discount-amount");
  var suffixEl = document.getElementById("discount-suffix");
  var list = document.getElementById("payments-list");
  var addBtn = document.getElementById("add-payment");
  var template = document.getElementById("payment-row-template");
  var form = document.getElementById("checkout-form");
  var submitBtn = document.getElementById("checkout-submit");

  // "12,34" ou "12.34" -> 1234 centavos (HALF_UP via Math.round).
  function parseCents(raw) {
    if (!raw) return 0;
    var value = parseFloat(String(raw).trim().replace(",", "."));
    if (isNaN(value) || value < 0) return 0;
    return Math.round(value * 100);
  }

  function formatCents(cents) {
    return "R$ " + (cents / 100).toFixed(2);
  }

  function discountCents() {
    var amount = parseFloat(String(amountEl.value || "0").replace(",", "."));
    if (isNaN(amount) || amount < 0) amount = 0;
    var cents;
    if (modeEl.value === "percent") {
      if (amount > 100) amount = 100;
      cents = Math.round((subtotalCents * amount) / 100);
    } else {
      cents = Math.round(amount * 100);
    }
    if (cents > subtotalCents) cents = subtotalCents;
    return cents;
  }

  function recompute() {
    var discount = discountCents();
    var total = subtotalCents - discount;

    var paid = 0;
    list.querySelectorAll(".payment-value").forEach(function (input) {
      paid += parseCents(input.value);
    });
    var change = paid > total ? paid - total : 0;

    document.getElementById("summary-subtotal").textContent = formatCents(subtotalCents);
    document.getElementById("summary-discount").textContent = formatCents(discount);
    document.getElementById("summary-total").textContent = formatCents(total);
    document.getElementById("summary-paid").textContent = formatCents(paid);
    document.getElementById("summary-change").textContent = formatCents(change);

    updateAllHints();
  }

  // Parcelas só fazem sentido no crédito; oculta nos demais tipos.
  function syncInstallments(row) {
    var type = row.querySelector(".payment-type");
    var wrap = row.querySelector(".payment-installments-wrap");
    if (!type || !wrap) return;
    wrap.classList.toggle("hidden", type.value !== CREDIT);
  }

  // Valor que falta pagar desconsiderando uma linha = total − soma das demais (≥ 0).
  function remainingExcluding(exceptRow) {
    var total = subtotalCents - discountCents();
    var paid = 0;
    list.querySelectorAll(".payment-row").forEach(function (row) {
      if (row === exceptRow) return;
      var input = row.querySelector(".payment-value");
      if (input) paid += parseCents(input.value);
    });
    var remaining = total - paid;
    return remaining > 0 ? remaining : 0;
  }

  // Mostra a sugestão abaixo do campo só quando ele está em branco e há saldo.
  function updateHint(row) {
    var input = row.querySelector(".payment-value");
    var hint = row.querySelector(".payment-hint");
    if (!input || !hint) return;
    var remaining = remainingExcluding(row);
    if (input.value.trim() === "" && remaining > 0) {
      hint.textContent = "Faltam R$ " + (remaining / 100).toFixed(2) + " — clique para preencher.";
      hint.setAttribute("data-fill", remaining);
      hint.style.display = "inline-flex";
    } else {
      hint.style.display = "none";
    }
  }

  function updateAllHints() {
    list.querySelectorAll(".payment-row").forEach(updateHint);
  }

  function addRow() {
    var fragment = template.content.cloneNode(true);
    list.appendChild(fragment);
    var row = list.lastElementChild;
    syncInstallments(row);
    recompute();
  }

  // Atualização ao vivo do desconto.
  function updateSuffix() {
    suffixEl.textContent = modeEl.value === "percent" ? "(%)" : "(R$)";
  }

  modeEl.addEventListener("change", function () {
    updateSuffix();
    recompute();
  });
  amountEl.addEventListener("input", recompute);

  // Grupo "Desconto": oculto por padrão, alternado pelo botão do cabeçalho.
  var discountToggle = document.getElementById("toggle-discount");
  var discountGroup = document.getElementById("discount-group");
  if (discountToggle && discountGroup) {
    // Reabre automaticamente se já houver desconto digitado (re-render pós-erro).
    if (amountEl.value.trim() !== "") {
      discountGroup.classList.remove("hidden");
      discountToggle.setAttribute("aria-expanded", "true");
    }
    discountToggle.addEventListener("click", function () {
      var open = discountGroup.classList.toggle("hidden") === false;
      discountToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  addBtn.addEventListener("click", addRow);

  // Delegação: lida com linhas adicionadas dinamicamente.
  list.addEventListener("input", function (event) {
    if (event.target.classList.contains("payment-value")) recompute();
  });
  list.addEventListener("change", function (event) {
    if (event.target.classList.contains("payment-type")) {
      syncInstallments(event.target.closest(".payment-row"));
    }
  });
  list.addEventListener("click", function (event) {
    // Clique na sugestão preenche o campo com o valor que falta pagar.
    var hint = event.target.closest(".payment-hint");
    if (hint) {
      var hintRow = hint.closest(".payment-row");
      var input = hintRow.querySelector(".payment-value");
      var cents = parseInt(hint.getAttribute("data-fill"), 10) || 0;
      if (input) {
        input.value = (cents / 100).toFixed(2);
        recompute();
        input.focus();
      }
      return;
    }

    var btn = event.target.closest(".remove-payment");
    if (!btn) return;
    var row = btn.closest(".payment-row");
    if (row) row.remove();
    recompute();
  });

  // Evita finalização duplicada (duplo-clique / reenvio).
  form.addEventListener("submit", function () {
    submitBtn.disabled = true;
    submitBtn.classList.add("opacity-60", "cursor-not-allowed");
  });

  // Estado inicial: garante ao menos uma linha de pagamento e sincroniza tudo.
  updateSuffix();
  if (list.querySelectorAll(".payment-row").length === 0) {
    addRow();
  } else {
    list.querySelectorAll(".payment-row").forEach(syncInstallments);
  }
  recompute();
})();
