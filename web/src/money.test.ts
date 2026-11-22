import { describe, expect, it } from "vitest";
import { formatMoney } from "./money";

describe("formatMoney", () => {
  it("formats BOB with Bolivian separators without converting to Number", () => {
    expect(formatMoney("0.00", "BOB")).toBe("Bs 0,00");
    expect(formatMoney("2625.94", "BOB")).toBe("Bs 2.625,94");
    expect(formatMoney("-1961.90", "BOB")).toBe("-Bs 1.961,90");
    expect(formatMoney("9007199254740993.01", "BOB"))
      .toBe("Bs 9.007.199.254.740.993,01");
  });

  it("keeps the exact currency scale for other currencies", () => {
    expect(formatMoney("12.50", "USDT")).toBe("12,50 USDT");
    expect(formatMoney("1.000000", "USDT")).toBe("1,000000 USDT");
  });

  it("does not render a negative sign for exact zero", () => {
    expect(formatMoney("-0.00", "BOB")).toBe("Bs 0,00");
    expect(formatMoney("-0.000000", "USDT")).toBe("0,000000 USDT");
  });
});
