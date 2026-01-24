const simulationButton = document.getElementById("simulate");
const simulationResult = document.getElementById("simulation-result");
const currentYear = document.getElementById("current-year");
const testimonials = document.querySelectorAll(".testimonial");
const faqItems = document.querySelectorAll(".faq__item");

const simulations = [
  "Geramos 120 jogos com orçamento de R$ 150 e estratégia híbrida.",
  "Criamos 80 jogos com foco em números quentes e filtragem avançada.",
  "Listas consolidadas com 45 combinações premium prontas para exportar.",
];

let testimonialIndex = 0;

if (currentYear) {
  currentYear.textContent = new Date().getFullYear();
}

if (simulationButton && simulationResult) {
  simulationButton.addEventListener("click", () => {
    const text = simulations[Math.floor(Math.random() * simulations.length)];
    simulationResult.textContent = text;
  });
}

if (testimonials.length > 0) {
  setInterval(() => {
    testimonials[testimonialIndex].classList.remove("is-active");
    testimonialIndex = (testimonialIndex + 1) % testimonials.length;
    testimonials[testimonialIndex].classList.add("is-active");
  }, 5000);
}

faqItems.forEach((item) => {
  item.addEventListener("click", () => {
    const content = item.nextElementSibling;
    if (!content) {
      return;
    }
    content.classList.toggle("is-open");
    item.querySelector(".faq__icon").textContent = content.classList.contains(
      "is-open",
    )
      ? "−"
      : "+";
  });
});
