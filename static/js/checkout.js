(function () {
  const form = document.getElementById("checkout-form");
  if (!form) return;

  const deliveryFields = document.getElementById("delivery-fields");
  const shippingAddress = document.getElementById("shipping-address");
  const customerPhone = document.getElementById("customer-phone");
  const shippingDisplay = document.getElementById("shipping-display");
  const totalDisplay = document.getElementById("total-display");
  const cashBtn = document.getElementById("pay-cash-btn");
  const subtotalCents = Number(form.dataset.subtotalCents || 0);
  const cyprusCents = Number(form.dataset.cyprusShippingCents || 0);
  const internationalCents = Number(form.dataset.internationalShippingCents || 0);

  function selectedMethod() {
    const checked = form.querySelector('input[name="shipping_method"]:checked');
    return checked ? checked.value : "pickup";
  }

  function selectedCountry() {
    const checked = form.querySelector('input[name="delivery_country"]:checked');
    return checked ? checked.value : "cyprus";
  }

  function shippingCents() {
    if (selectedMethod() === "pickup") return 0;
    return selectedCountry() === "other" ? internationalCents : cyprusCents;
  }

  function formatMoney(cents) {
    return "€" + (cents / 100).toFixed(2);
  }

  function updateTotals() {
    const isDelivery = selectedMethod() === "delivery";
    if (deliveryFields) {
      deliveryFields.classList.toggle("is-hidden", !isDelivery);
      deliveryFields.disabled = !isDelivery;
    }
    if (shippingAddress) {
      shippingAddress.required = isDelivery;
    }
    if (customerPhone) {
      customerPhone.required = isDelivery;
    }
    if (cashBtn) {
      cashBtn.disabled = isDelivery;
    }
    const ship = shippingCents();
    if (shippingDisplay) {
      if (ship === 0) {
        shippingDisplay.innerHTML = '<span class="free-badge">Free</span>';
      } else {
        shippingDisplay.textContent = formatMoney(ship);
      }
    }
    if (totalDisplay) {
      totalDisplay.innerHTML = "<strong>" + formatMoney(subtotalCents + ship) + "</strong>";
    }
  }

  form.querySelectorAll('input[name="shipping_method"]').forEach((el) => {
    el.addEventListener("change", updateTotals);
  });
  form.querySelectorAll('input[name="delivery_country"]').forEach((el) => {
    el.addEventListener("change", updateTotals);
  });
  updateTotals();
})();
