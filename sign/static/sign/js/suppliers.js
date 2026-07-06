// Linhas dinâmicas de representantes no form de criação de fornecedor.
// Clona o <template> e liga as máscaras dos telefones da nova linha via
// window.bindMasks (definido em masks.js). Ver views.suppliers.SupplierCreateView,
// que parseia os inputs paralelos (rep_name/rep_email/rep_phone_*) do POST.
(function () {
    var list = document.getElementById("representatives-list");
    var addBtn = document.getElementById("add-representative");
    var template = document.getElementById("representative-row-template");
    if (!list || !addBtn || !template) return;

    function addRow() {
        var fragment = template.content.cloneNode(true);
        list.appendChild(fragment);
        var row = list.lastElementChild;
        if (window.bindMasks) window.bindMasks(row);
        var firstInput = row.querySelector('input[name="rep_name"]');
        if (firstInput) firstInput.focus();
    }

    addBtn.addEventListener("click", addRow);

    list.addEventListener("click", function (event) {
        var btn = event.target.closest(".remove-representative");
        if (!btn) return;
        var row = btn.closest(".representative-row");
        if (row) row.remove();
    });
})();
