(function () {
  const form = document.getElementById("checkout-form");
  if (!form) return;

  const deliveryFields = document.getElementById("delivery-fields");
  const deliveryCountry = document.getElementById("delivery-country");
  const shippingAddress = document.getElementById("shipping-address");
  const customerPhone = document.getElementById("customer-phone");
  const shippingDisplay = document.getElementById("shipping-display");
  const totalDisplay = document.getElementById("total-display");
  const subtotalCents = Number(form.dataset.subtotalCents || 0);
  const cyprusCents = Number(form.dataset.cyprusShippingCents || 0);
  const internationalCents = Number(form.dataset.internationalShippingCents || 0);

  function selectedMethod() {
    const checked = form.querySelector('input[name="shipping_method"]:checked');
    return checked ? checked.value : "pickup";
  }

  function shippingCents() {
    if (selectedMethod() === "pickup") return 0;
    return deliveryCountry && deliveryCountry.value === "other" ? internationalCents : cyprusCents;
  }

  function formatMoney(cents) {
    return "€" + (cents / 100).toFixed(2);
  }

  function selectedPay() {
    const checked = form.querySelector('input[name="payment_method"]:checked');
    return checked ? checked.value : "card";
  }

  function updateTotals() {
    const isDelivery = selectedMethod() === "delivery";
    const isPickup = !isDelivery;
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
    const cashRadio = form.querySelector('input[name="payment_method"][value="cash"]');
    const cardRadio = form.querySelector('input[name="payment_method"][value="card"]');
    if (!isPickup && cashRadio && cashRadio.checked && cardRadio) {
      cardRadio.checked = true;
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
    const submit = document.getElementById("checkout-submit");
    const paymentsOn = form.dataset.paymentsOn === "1";
    const payCash = selectedPay() === "cash" && isPickup;
    if (submit) {
      if (payCash) {
        submit.textContent = "Place order — pay at pick up";
      } else if (paymentsOn) {
        submit.textContent = "Pay with card";
      } else {
        submit.textContent = "Place order";
      }
    }
  }

  form.querySelectorAll('input[name="shipping_method"]').forEach((el) => {
    el.addEventListener("change", updateTotals);
  });
  form.querySelectorAll('input[name="payment_method"]').forEach((el) => {
    el.addEventListener("change", updateTotals);
  });
  if (deliveryCountry) {
    deliveryCountry.addEventListener("change", updateTotals);
  }
  updateTotals();
})();
