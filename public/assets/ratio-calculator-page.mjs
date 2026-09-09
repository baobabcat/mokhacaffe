import { calculateCoffee, calculateWater } from "/assets/ratio-calculator.mjs";

const form = document.querySelector("#ratio-form");
const amountInput = document.querySelector("#amount");
const ratioInput = document.querySelector("#ratio");
const result = document.querySelector("#result");

function selectedDirection() {
  return new FormData(form).get("direction");
}

function showResult() {
  const amount = Number(amountInput.value);
  const ratio = Number(ratioInput.value);
  const direction = selectedDirection();

  try {
    if (direction === "water") {
      const coffee = calculateCoffee(amount, ratio);
      result.textContent = `Use ${coffee} g of coffee for ${amount} g of water.`;
    } else {
      const water = calculateWater(amount, ratio);
      result.textContent = `Use ${water} g of water for ${amount} g of coffee.`;
    }
  } catch {
    result.textContent = "Enter numbers greater than zero for the amount and ratio.";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  showResult();

  if (typeof window.gtag === "function") {
    window.gtag("event", "ratio_calculation", {
      calculation_direction: selectedDirection(),
    });
  }
});

form.addEventListener("input", showResult);
