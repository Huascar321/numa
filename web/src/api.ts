export type Currency = {
  code: string;
  decimal_places: number;
};

export type Plan = {
  id: string;
  name: string;
  reporting_currency_code: string;
  created_at: string;
  updated_at: string;
};

export const ACCOUNT_TYPES = [
  "Bank",
  "Cash",
  "Wallet",
  "Credit Card",
  "Crypto",
  "Other",
] as const;

export type AccountType = (typeof ACCOUNT_TYPES)[number];
export type AccountStatus = "active" | "archived";

export type Balance = {
  amount: string;
  currency: string;
};

export type Account = {
  id: string;
  plan_id: string;
  name: string;
  account_type: AccountType;
  currency_code: string;
  status: AccountStatus;
  balance: Balance;
  created_at: string;
  updated_at: string;
};

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  const body = (await response.json()) as unknown;
  if (!response.ok) {
    const detail = typeof body === "object" && body !== null && "detail" in body
      && typeof body.detail === "string"
      ? body.detail
      : "The server rejected the request.";
    throw new ApiError(response.status, detail);
  }
  return body as T;
}

export function newClientId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
    const random = Math.random() * 16;
    const value = character === "x" ? random : (random & 0x3) | 0x8;
    return Math.floor(value).toString(16);
  });
}

export function getCurrencies(): Promise<Currency[]> {
  return request<Currency[]>("/currencies");
}

export function getPlans(): Promise<Plan[]> {
  return request<Plan[]>("/plans");
}

export function getPlan(planId: string): Promise<Plan> {
  return request<Plan>(`/plans/${planId}`);
}

export function createPlan(
  planId: string,
  payload: Pick<Plan, "name" | "reporting_currency_code">,
): Promise<Plan> {
  return request<Plan>(`/plans/${planId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function renamePlan(planId: string, name: string): Promise<Plan> {
  return request<Plan>(`/plans/${planId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export function getAccounts(planId: string): Promise<Account[]> {
  return request<Account[]>(`/plans/${planId}/accounts`);
}

export function createAccount(
  planId: string,
  accountId: string,
  payload: Pick<Account, "name" | "account_type" | "currency_code">,
): Promise<Account> {
  return request<Account>(`/plans/${planId}/accounts/${accountId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function renameAccount(
  planId: string,
  accountId: string,
  name: string,
): Promise<Account> {
  return request<Account>(`/plans/${planId}/accounts/${accountId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export function archiveAccount(
  planId: string,
  accountId: string,
): Promise<Account> {
  return request<Account>(`/plans/${planId}/accounts/${accountId}/archive`, {
    method: "POST",
  });
}
