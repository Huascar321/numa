const PREFIXED_CURRENCIES: Record<string, string> = {
  BOB: "Bs",
};

/**
 * Formats an exact decimal string without converting it to Number.
 * The UI uses Bolivian conventions: dot for thousands and comma for decimals.
 * The original server string remains the source of truth for requests and
 * accessible labels that need an exact value.
 */
export function formatMoney(value: string, currency: string): string {
  const normalized = value.trim();
  const negative = normalized.startsWith("-");
  const unsigned = negative ? normalized.slice(1) : normalized;
  const isZero = /^0*(?:\.0*)?$/.test(unsigned);
  const [whole = "0", fraction = ""] = unsigned.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const amount = fraction ? `${grouped},${fraction}` : grouped;
  const sign = negative && !isZero ? "-" : "";
  const code = currency.trim().toUpperCase();
  const prefix = PREFIXED_CURRENCIES[code];
  if (prefix) return `${sign}${prefix} ${amount}`;
  return `${sign}${amount}${code ? ` ${code}` : ""}`;
}

export function formatTransactionDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

export function toDateTimeLocal(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16);
}
