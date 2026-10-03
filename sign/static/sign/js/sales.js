// Modais da declaração de venda (listagem e detalhe).
// Só mecânica de abrir/fechar: o envio é um POST de formulário comum, validado
// e gravado no backend, que recarrega a tela com a mensagem de sucesso.
(function () {
  "use strict";

  function openModal(modal) {
    modal.classList.remove("hidden");
    modal.classList.add("flex");
  }

  function closeModal(modal) {
    modal.classList.add("hidden");
    modal.classList.remove("flex");
  }

  // Fechar por backdrop, Escape e botão de cancelar — igual aos demais modais.
  function bindDismiss(modal, cancelBtn) {
    if (cancelBtn) {
      cancelBtn.addEventListener("click", function () {
        closeModal(modal);
      });
    }
    modal.addEventListener("click", function (event) {
      if (event.target === modal) closeModal(modal);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !modal.classList.contains("hidden")) {
        closeModal(modal);
      }
    });
  }

  // ----- Declarar venda (modal compartilhado por todas as linhas) -----
  function initDeclareModal() {
    var modal = document.getElementById("sale-declare-modal");
    if (!modal) return;

    var form = document.getElementById("sale-declare-form");
    var input = document.getElementById("sale-declare-input");
    var label = document.getElementById("sale-declare-label");
    // "Agora" renderizado pelo servidor, já no fuso configurado na empresa —
    // guardado aqui para repor o campo a cada abertura.
    var initialValue = input ? input.value : "";

    document.querySelectorAll(".sale-declare-btn").forEach(function (button) {
      button.addEventListener("click", function () {
        form.action = button.getAttribute("data-url");
        if (label) label.textContent = button.getAttribute("data-sale") || "";
        if (input) input.value = initialValue;
        openModal(modal);
        if (input) input.focus();
      });
    });

    bindDismiss(modal, document.getElementById("sale-declare-cancel"));
  }

  // ----- Desfazer declaração (só na tela de detalhe) -----
  function initUndeclareModal() {
    var modal = document.getElementById("sale-undeclare-modal");
    if (!modal) return;

    document.querySelectorAll(".sale-undeclare-btn").forEach(function (button) {
      button.addEventListener("click", function () {
        openModal(modal);
      });
    });

    bindDismiss(modal, document.getElementById("sale-undeclare-cancel"));
  }

  document.addEventListener("DOMContentLoaded", function () {
    initDeclareModal();
    initUndeclareModal();
  });
})();
