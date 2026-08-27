(function () {
  const main = document.getElementById("gallery-main");
  if (!main) return;
  document.querySelectorAll("[data-gallery-src]").forEach(function (button) {
    button.addEventListener("click", function () {
      const src = button.getAttribute("data-gallery-src");
      if (!src) return;
      main.setAttribute("src", src);
      document.querySelectorAll("[data-gallery-src]").forEach(function (other) {
        other.classList.toggle("is-active", other === button);
      });
    });
  });
})();
