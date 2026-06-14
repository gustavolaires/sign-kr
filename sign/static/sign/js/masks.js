// Máscaras puramente visuais para inputs com [data-mask].
// O valor real gravado é limpo no backend (forms.ClientForm.clean_*),
// então aqui só formatamos o que o usuário vê enquanto digita.
(function () {
    function onlyDigits(value) {
        return (value || "").replace(/\D/g, "");
    }

    function formatCpfCnpj(value) {
        var d = onlyDigits(value).slice(0, 14);
        if (d.length <= 11) {
            // CPF: 000.000.000-00
            if (d.length > 9) return d.slice(0, 3) + "." + d.slice(3, 6) + "." + d.slice(6, 9) + "-" + d.slice(9);
            if (d.length > 6) return d.slice(0, 3) + "." + d.slice(3, 6) + "." + d.slice(6);
            if (d.length > 3) return d.slice(0, 3) + "." + d.slice(3);
            return d;
        }
        // CNPJ: 00.000.000/0000-00
        var out = d.slice(0, 2) + "." + d.slice(2, 5) + "." + d.slice(5, 8) + "/" + d.slice(8, 12);
        if (d.length > 12) out += "-" + d.slice(12);
        return out;
    }

    function formatPhone(value) {
        var d = onlyDigits(value).slice(0, 11);
        if (d.length === 0) return "";
        if (d.length <= 2) return "(" + d;
        if (d.length <= 6) return "(" + d.slice(0, 2) + ") " + d.slice(2);
        if (d.length <= 10) return "(" + d.slice(0, 2) + ") " + d.slice(2, 6) + "-" + d.slice(6);
        // celular: (00) 00000-0000
        return "(" + d.slice(0, 2) + ") " + d.slice(2, 7) + "-" + d.slice(7);
    }

    function formatCep(value) {
        var d = onlyDigits(value).slice(0, 8);
        if (d.length <= 5) return d;
        return d.slice(0, 5) + "-" + d.slice(5);
    }

    var formatters = {
        "cpf-cnpj": formatCpfCnpj,
        "phone": formatPhone,
        "cep": formatCep,
    };

    document.querySelectorAll("[data-mask]").forEach(function (el) {
        var format = formatters[el.getAttribute("data-mask")];
        if (!format) return;
        var apply = function () {
            el.value = format(el.value);
        };
        apply(); // formata o valor pré-preenchido (edição)
        el.addEventListener("input", apply);
    });
})();
