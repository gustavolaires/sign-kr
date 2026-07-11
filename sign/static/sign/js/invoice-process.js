// Tela de confirmação do processamento da NF de entrada.
// - Alterna entre "produto associado" e "produto novo" (habilita/oculta os
//   selects correspondentes).
// - Sinaliza quando o preço de venda ficaria MENOR que o preço atual do produto
//   associado (só para produtos existentes). Ver views.invoices.invoice_process.
(function () {
    function toCents(value) {
        var reais = parseFloat(String(value).replace(",", "."));
        if (isNaN(reais)) return null;
        return Math.round(reais * 100);
    }

    function wireRow(row) {
        var isNew = row.querySelector('[data-role="is-new"]');
        var existingFields = row.querySelector('[data-role="existing-fields"]');
        var newFields = row.querySelector('[data-role="new-fields"]');
        var product = row.querySelector('[data-role="product"]');
        var manufacturer = row.querySelector('[data-role="manufacturer"]');
        var price = row.querySelector('[data-role="price"]');
        var alertEl = row.querySelector('[data-role="price-alert"]');

        function currentPriceCents() {
            if (!product) return null;
            var opt = product.options[product.selectedIndex];
            if (!opt || !opt.value) return null;
            var cents = parseInt(opt.getAttribute("data-price-cents"), 10);
            return isNaN(cents) ? null : cents;
        }

        function updateAlert() {
            if (!alertEl) return;
            if (isNew.checked) {
                alertEl.classList.add("hidden");
                return;
            }
            var current = currentPriceCents();
            var next = toCents(price.value);
            var lower = current !== null && next !== null && next < current;
            alertEl.classList.toggle("hidden", !lower);
        }

        function toggleMode() {
            var newProduct = isNew.checked;
            if (existingFields) existingFields.classList.toggle("hidden", newProduct);
            if (newFields) newFields.classList.toggle("hidden", !newProduct);
            if (product) product.disabled = newProduct;
            if (manufacturer) manufacturer.disabled = !newProduct;
            updateAlert();
        }

        if (isNew) isNew.addEventListener("change", toggleMode);
        if (product) product.addEventListener("change", updateAlert);
        if (price) price.addEventListener("input", updateAlert);

        // Estado inicial (respeita a sugestão vinda do servidor).
        updateAlert();
    }

    document.addEventListener("DOMContentLoaded", function () {
        var container = document.getElementById("process-items");
        if (!container) return;
        container.querySelectorAll("[data-item-id]").forEach(wireRow);
    });
})();
