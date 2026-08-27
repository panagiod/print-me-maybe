(function () {
  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;

    const status = form.querySelector('select[name="status"]');
    if (status instanceof HTMLSelectElement && status.value === "cancelled") {
      const current = form.getAttribute("data-current-status") || "";
      if (current !== "cancelled") {
        let message = "Cancel this order? Items go back in stock.";
        if (form.getAttribute("data-card-paid") === "1") {
          const amount = form.getAttribute("data-refund-amount") || "the payment";
          message =
            "Cancel this order and refund " +
            amount +
            " to the card? Stripe keeps the original processing fee.";
        } else if (form.getAttribute("data-paid") === "1") {
          message =
            "Cancel this paid order? Stock will go back. This will not refund a card payment.";
        }
        if (!window.confirm(message)) {
          event.preventDefault();
        }
        return;
      }
    }

    const confirmMessage = form.getAttribute("data-confirm");
    if (confirmMessage && !window.confirm(confirmMessage)) {
      event.preventDefault();
    }
  });

  document.querySelectorAll("[data-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      const text = button.getAttribute("data-copy") || "";
      if (!text) return;
      const original = button.textContent;
      function markCopied() {
        button.textContent = "Copied";
        window.setTimeout(function () {
          button.textContent = original;
        }, 1600);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(markCopied).catch(function () {
          window.prompt("Copy this link", text);
        });
        return;
      }
      window.prompt("Copy this link", text);
    });
  });
  document.querySelectorAll("[data-print]").forEach(function (button) {
    button.addEventListener("click", function () {
      window.print();
    });
  });
})();
