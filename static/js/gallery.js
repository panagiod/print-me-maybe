(function () {
  document.querySelectorAll("[data-gallery]").forEach(function (root) {
    const viewport = root.querySelector(".gallery-viewport");
    if (!viewport) return;

    const slides = Array.from(root.querySelectorAll("[data-gallery-slide]"));
    const thumbs = Array.from(root.querySelectorAll("[data-gallery-index]"));
    const prev = root.querySelector("[data-gallery-prev]");
    const next = root.querySelector("[data-gallery-next]");
    if (slides.length < 2) return;

    function currentIndex() {
      const width = viewport.clientWidth || 1;
      return Math.max(0, Math.min(slides.length - 1, Math.round(viewport.scrollLeft / width)));
    }

    function sync(index) {
      thumbs.forEach(function (thumb, i) {
        thumb.classList.toggle("is-active", i === index);
      });
    }

    function go(index) {
      const clamped = Math.max(0, Math.min(slides.length - 1, index));
      viewport.scrollTo({ left: clamped * viewport.clientWidth, behavior: "smooth" });
      sync(clamped);
    }

    if (prev) {
      prev.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        go(currentIndex() - 1);
      });
    }
    if (next) {
      next.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        go(currentIndex() + 1);
      });
    }
    thumbs.forEach(function (thumb, i) {
      thumb.addEventListener("click", function () {
        go(i);
      });
    });
    viewport.addEventListener(
      "scroll",
      function () {
        sync(currentIndex());
      },
      { passive: true }
    );
    viewport.addEventListener("keydown", function (event) {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        go(currentIndex() - 1);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        go(currentIndex() + 1);
      }
    });
  });
})();
