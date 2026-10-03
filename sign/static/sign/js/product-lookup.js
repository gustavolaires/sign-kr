// Lupa de busca de produto no campo "Código" de um item de NF de entrada.
// Consulta sign:invoice_item_product_lookup (que casa o código contra o
// nf_search_id dos produtos, respeitando o fornecedor mono-marca) e preenche
// Descrição e Tipo de unidade. Serve tanto às linhas clonadas do form de nova
// NF quanto à página isolada de produto da NF — cada escopo é um elemento com
// [data-lookup-scope]. Ver views.invoices.invoice_item_product_lookup.
(function () {
  "use strict";

  var modal = document.getElementById("product-lookup-modal");
  if (!modal) return;

  var lookupUrl = modal.getAttribute("data-lookup-url");
  var optionsBox = document.getElementById("product-lookup-options");
  var optionTemplate = document.getElementById("product-lookup-option-template");
  var codeLabel = document.getElementById("product-lookup-code");
  var confirmBtn = document.getElementById("product-lookup-confirm");
  var cancelBtn = document.getElementById("product-lookup-cancel");

  // Escopo cuja lupa abriu o modal e opções exibidas, enquanto ele está aberto.
  var pendingScope = null;
  var pendingResults = [];

  // ----- Feedback inline (abaixo do campo Código) -----

  var FEEDBACK_TONES = {
    info: "text-amber-700",
    success: "text-green-700",
    error: "text-red-600",
  };

  function showFeedback(scope, tone, message) {
    var el = scope.querySelector('[data-role="lookup-feedback"]');
    if (!el) return;
    el.textContent = message;
    el.className = "mt-1 text-xs " + (FEEDBACK_TONES[tone] || FEEDBACK_TONES.info);
  }

  function clearFeedback(scope) {
    var el = scope.querySelector('[data-role="lookup-feedback"]');
    if (!el) return;
    el.textContent = "";
    el.className = "mt-1 hidden text-xs";
  }

  // ----- Preenchimento -----

  // Aplica o produto escolhido ao escopo: descrição ← nome do produto (mesma
  // correspondência que process_inbound_invoice usa ao criar o produto).
  function applyProduct(scope, product) {
    var description = scope.querySelector('[data-role="lookup-description"]');
    var unitType = scope.querySelector('[data-role="lookup-unit-type"]');
    if (description) description.value = product.name;
    if (unitType) {
      // Só troca se a sigla existir entre as opções (guarda defensiva).
      for (var i = 0; i < unitType.options.length; i++) {
        if (unitType.options[i].value === product.unit_type) {
          unitType.value = product.unit_type;
          break;
        }
      }
    }
    showFeedback(scope, "success", 'Preenchido com "' + product.name + '".');
  }

  // ----- Modal -----

  function optionDetails(product) {
    var parts = [product.manufacturer];
    if (product.manufacturer_code) parts.push("cód. " + product.manufacturer_code);
    if (product.barcode) parts.push("barras " + product.barcode);
    parts.push(product.unit_type);
    return parts.join(" · ");
  }

  function renderOptions(results) {
    optionsBox.innerHTML = "";
    results.forEach(function (product, index) {
      var fragment = optionTemplate.content.cloneNode(true);
      var radio = fragment.querySelector("input[type=radio]");
      radio.value = String(index);
      if (index === 0) radio.checked = true;
      fragment.querySelector('[data-role="option-name"]').textContent = product.name;
      fragment.querySelector('[data-role="option-details"]').textContent =
        optionDetails(product);
      if (!product.is_active) {
        fragment.querySelector('[data-role="option-inactive"]').classList.remove("hidden");
      }
      optionsBox.appendChild(fragment);
    });
  }

  function openModal(scope, code, results) {
    pendingScope = scope;
    pendingResults = results;
    codeLabel.textContent = code;
    renderOptions(results);
    modal.classList.remove("hidden");
    modal.classList.add("flex");
  }

  function closeModal() {
    pendingScope = null;
    pendingResults = [];
    modal.classList.add("hidden");
    modal.classList.remove("flex");
  }

  confirmBtn.addEventListener("click", function () {
    var checked = optionsBox.querySelector("input[type=radio]:checked");
    if (!checked || !pendingScope) return closeModal();
    var product = pendingResults[parseInt(checked.value, 10)];
    var scope = pendingScope;
    closeModal();
    if (product) applyProduct(scope, product);
  });

  cancelBtn.addEventListener("click", closeModal);

  modal.addEventListener("click", function (event) {
    if (event.target === modal) closeModal();
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !modal.classList.contains("hidden")) closeModal();
  });

  // ----- Busca -----

  // Fornecedor: o <select> do form da NF, ou o id fixo da nota na página de item.
  function supplierId(scope) {
    var select = document.getElementById("id_supplier");
    if (select) return select.value || "";
    return scope.getAttribute("data-supplier-id") || "";
  }

  function search(scope, button) {
    var input = scope.querySelector('[data-role="lookup-code"]');
    if (!input) return;
    var code = input.value.trim();
    if (!code) return;

    var icon = button.querySelector("i");
    var originalIcon = icon ? icon.className : "";
    button.disabled = true;
    if (icon) icon.className = "fa-solid fa-spinner fa-spin";
    clearFeedback(scope);

    var url =
      lookupUrl +
      "?code=" +
      encodeURIComponent(code) +
      "&supplier=" +
      encodeURIComponent(supplierId(scope));

    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (response) {
        return response.json().then(function (json) {
          return { ok: response.ok, data: json };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.data.ok) {
          showFeedback(
            scope,
            "error",
            result.data.error || "Não foi possível buscar o produto."
          );
          return;
        }
        var results = result.data.results;
        if (!results.length) {
          showFeedback(
            scope,
            "info",
            'Nenhum produto cadastrado com o código "' +
              code +
              '". Pode ser o caso de um produto novo.'
          );
        } else if (results.length === 1) {
          applyProduct(scope, results[0]);
        } else {
          openModal(scope, code, results);
        }
      })
      .catch(function () {
        showFeedback(scope, "error", "Não foi possível buscar o produto.");
      })
      .then(function () {
        button.disabled = false;
        if (icon) icon.className = originalIcon;
      });
  }

  // ----- Ligação com o DOM (delegação: cobre as linhas clonadas da NF) -----

  // O botão só aparece depois que há algo digitado no código.
  function syncButton(input) {
    var scope = input.closest("[data-lookup-scope]");
    if (!scope) return;
    var button = scope.querySelector('[data-role="lookup-search"]');
    if (button) button.classList.toggle("hidden", !input.value.trim());
  }

  document.addEventListener("input", function (event) {
    var input = event.target.closest('[data-role="lookup-code"]');
    if (input) syncButton(input);
  });

  document.addEventListener("click", function (event) {
    var button = event.target.closest('[data-role="lookup-search"]');
    if (!button) return;
    var scope = button.closest("[data-lookup-scope]");
    if (scope) search(scope, button);
  });

  // Campo já preenchido ao carregar (edição de um produto da nota).
  Array.prototype.forEach.call(
    document.querySelectorAll('[data-role="lookup-code"]'),
    syncButton
  );
})();
