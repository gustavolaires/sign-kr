// Linhas dinâmicas de faturas e produtos no form de criação de NF de entrada.
// Clona os <template> e injeta as linhas. Ver views.invoices.InboundInvoiceCreateView,
// que parseia os inputs paralelos (dup_*/item_*) do POST via _collect_rows.
(function () {
    function wireRepeater(listId, addBtnId, templateId, rowClass, removeClass) {
        var list = document.getElementById(listId);
        var addBtn = document.getElementById(addBtnId);
        var template = document.getElementById(templateId);
        if (!list || !addBtn || !template) return;

        function addRow() {
            var fragment = template.content.cloneNode(true);
            list.appendChild(fragment);
            var row = list.lastElementChild;
            var firstInput = row.querySelector("input, select");
            if (firstInput) firstInput.focus();
        }

        addBtn.addEventListener("click", addRow);

        list.addEventListener("click", function (event) {
            var btn = event.target.closest("." + removeClass);
            if (!btn) return;
            var row = btn.closest("." + rowClass);
            if (row) row.remove();
        });
    }

    wireRepeater(
        "duplicates-list", "add-duplicate", "duplicate-row-template",
        "duplicate-row", "remove-duplicate"
    );
    wireRepeater(
        "items-list", "add-item", "item-row-template",
        "item-row", "remove-item"
    );
})();
