function requirePositive(value, label) {
  if (!Number.isFinite(value) || value <= 0) {
    throw new RangeError(`${label} must be greater than zero`);
  }
}

function requireRatio(value) {
  if (!Number.isFinite(value) || value < 1) {
    throw new RangeError("Ratio must be at least one");
  }
}

function roundAmount(value) {
  if (!Number.isFinite(value) || Math.abs(value) > Number.MAX_VALUE / 10) {
    throw new RangeError("Calculated amount is too large");
  }
  return Math.round((value + Number.EPSILON) * 10) / 10;
}

export function calculateCoffee(waterGrams, ratio) {
  requirePositive(waterGrams, "Water");
  requireRatio(ratio);
  return roundAmount(waterGrams / ratio);
}

export function calculateWater(coffeeGrams, ratio) {
  requirePositive(coffeeGrams, "Coffee");
  requireRatio(ratio);
  return roundAmount(coffeeGrams * ratio);
}
