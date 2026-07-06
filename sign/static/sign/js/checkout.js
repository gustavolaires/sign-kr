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

  // ----- Calculadora de desconto (modal com range sliders, estilo ábaco) -----
  var calcModal = document.getElementById("discount-calc-modal");
  var calcData = document.getElementById("calc-items-data");
  if (calcModal && calcData) {
    var openCalcBtn = document.getElementById("open-discount-calc");
    var calcClose = document.getElementById("calc-close");
    var calcCancel = document.getElementById("calc-cancel");
    var calcApply = document.getElementById("calc-apply");
    var calcTypeBtns = calcModal.querySelectorAll(".calc-type-btn");
    var calcTotalSection = document.getElementById("calc-total-section");
    var calcProductSection = document.getElementById("calc-product-section");
    var calcTotalSlider = document.getElementById("calc-total-slider");
    var calcTotalPct = document.getElementById("calc-total-pct");
    var calcTotalValue = document.getElementById("calc-total-value");
    var calcProductList = document.getElementById("calc-product-list");
    var calcRowTemplate = document.getElementById("calc-product-row-template");
    var calcTotalDiscount = document.getElementById("calc-total-discount");
    var discountObsEl = document.getElementById("id_discount_obs");

    var calcItems = [];
    try {
      calcItems = JSON.parse(calcData.textContent) || [];
    } catch (e) {
      calcItems = [];
    }

    var calcMode = "total"; // "total" | "product"

    // pt-BR: 123456 centavos -> "R$ 1.234,56".
    function formatBRL(cents) {
      return "R$ " + (cents / 100).toLocaleString("pt-BR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    }

    // Monta um slider por produto a partir dos dados do servidor.
    var productRows = [];
    calcItems.forEach(function (item) {
      var frag = calcRowTemplate.content.cloneNode(true);
      var row = frag.querySelector(".calc-product-row");
      row.querySelector(".calc-product-label").textContent = item.label;
      productRows.push({
        item: item,
        slider: row.querySelector(".calc-product-slider"),
        pctEl: row.querySelector(".calc-product-pct"),
        valueEl: row.querySelector(".calc-product-value"),
      });
      calcProductList.appendChild(frag);
    });
    if (calcItems.length === 0) {
      calcProductList.innerHTML =
        '<p class="text-sm text-gray-500">Nenhum produto no carrinho.</p>';
    }

    function totalModeDiscountCents() {
      var pct = parseInt(calcTotalSlider.value, 10) || 0;
      return Math.round((subtotalCents * pct) / 100);
    }

    function productRowDiscountCents(pr) {
      var pct = parseInt(pr.slider.value, 10) || 0;
      return Math.round((pr.item.subtotal_cents * pct) / 100);
    }

    function calcDiscountCents() {
      if (calcMode === "product") {
        var sum = 0;
        productRows.forEach(function (pr) {
          sum += productRowDiscountCents(pr);
        });
        return sum;
      }
      return totalModeDiscountCents();
    }

    // Atualiza os rótulos (% e R$) de cada slider e o total exibido.
    function refreshCalc() {
      calcTotalPct.textContent = (parseInt(calcTotalSlider.value, 10) || 0) + "%";
      calcTotalValue.textContent = formatBRL(totalModeDiscountCents());
      productRows.forEach(function (pr) {
        pr.pctEl.textContent = (parseInt(pr.slider.value, 10) || 0) + "%";
        pr.valueEl.textContent = formatBRL(productRowDiscountCents(pr));
      });
      calcTotalDiscount.textContent = formatBRL(calcDiscountCents());
    }

    // Alterna o tipo: destaca o botão ativo e habilita/esmaece cada seção.
    function setMode(mode) {
      calcMode = mode;
      calcTypeBtns.forEach(function (btn) {
        var active = btn.getAttribute("data-mode") === mode;
        btn.classList.toggle("bg-blue-600", active);
        btn.classList.toggle("text-white", active);
        btn.classList.toggle("text-gray-700", !active);
      });
      var totalActive = mode === "total";
      calcTotalSlider.disabled = !totalActive;
      calcTotalSection.classList.toggle("opacity-40", !totalActive);
      calcProductSection.classList.toggle("opacity-40", totalActive);
      productRows.forEach(function (pr) {
        pr.slider.disabled = totalActive;
      });
      refreshCalc();
    }

    function openCalc() {
      calcModal.classList.remove("hidden");
      calcModal.classList.add("flex");
    }

    function closeCalc() {
      calcModal.classList.add("hidden");
      calcModal.classList.remove("flex");
    }

    // Texto-resumo gravado nas "Observações do desconto".
    function buildSummary(totalCents) {
      if (calcMode === "product") {
        var parts = [];
        productRows.forEach(function (pr) {
          var cents = productRowDiscountCents(pr);
          if (cents > 0) {
            var pct = parseInt(pr.slider.value, 10) || 0;
            parts.push(pr.item.label + " - " + formatBRL(cents) + " (" + pct + "%)");
          }
        });
        if (parts.length === 0) return "";
        return "Desconto por produto: " + parts.join("; ") + ". Total " + formatBRL(totalCents) + ".";
      }
      var totalPct = parseInt(calcTotalSlider.value, 10) || 0;
      return "Desconto por valor total: " + formatBRL(totalCents) + " (" + totalPct + "%).";
    }

    function applyCalc() {
      var cents = calcDiscountCents();
      if (cents > subtotalCents) cents = subtotalCents;
      // Preenche o desconto como valor (R$) e sincroniza o modo do checkout.
      modeEl.value = "value";
      amountEl.value = (cents / 100).toFixed(2);
      if (discountObsEl) discountObsEl.value = buildSummary(cents);
      // Reusa os handlers existentes (sufixo + recálculo do resumo).
      modeEl.dispatchEvent(new Event("change"));
      amountEl.dispatchEvent(new Event("input"));
      // Garante o grupo de desconto visível.
      if (discountGroup) {
        discountGroup.classList.remove("hidden");
        if (discountToggle) discountToggle.setAttribute("aria-expanded", "true");
      }
      closeCalc();
    }

    if (openCalcBtn) openCalcBtn.addEventListener("click", openCalc);
    if (calcClose) calcClose.addEventListener("click", closeCalc);
    if (calcCancel) calcCancel.addEventListener("click", closeCalc);
    if (calcApply) calcApply.addEventListener("click", applyCalc);
    // Fecha ao clicar no backdrop (fora do card).
    calcModal.addEventListener("click", function (event) {
      if (event.target === calcModal) closeCalc();
    });
    calcTypeBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        setMode(btn.getAttribute("data-mode"));
      });
    });
    calcTotalSlider.addEventListener("input", refreshCalc);
    calcProductList.addEventListener("input", function (event) {
      if (event.target.classList.contains("calc-product-slider")) refreshCalc();
    });

    setMode("total");
  }
})();
