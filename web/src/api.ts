export type Currency = {
  code: string;
  decimal_places: number;
};

export type Plan = {
  id: string;
  name: string;
  reporting_currency_code: string;
  budget_timezone?: string;
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

export type CategoryGroup = {
  id: string;
  plan_id: string;
  name: string;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
};

export type Category = {
  id: string;
  plan_id: string;
  group_id: string | null;
  name: string;
  is_pending: boolean;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
};

export type Tag = {
  id: string;
  plan_id: string;
  name: string;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
};

export type Transaction = {
  id: string;
  plan_id: string;
  account_id: string;
  type: "income" | "expense";
  amount: string;
  currency_code: string;
  event_at: string;
  category_id: string;
  merchant: string | null;
  memo: string | null;
  photo_reference: string | null;
  location: Record<string, unknown> | null;
  tags: string[];
  source: string;
  source_metadata: Record<string, unknown>;
  provenance: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type TransactionCorrection = {
  id: string;
  plan_id: string;
  transaction_id: string;
  correction_sequence: number;
  before_snapshot: Record<string, unknown>;
  after_snapshot: Record<string, unknown>;
  provenance: Record<string, unknown>;
  created_at: string;
};

export type BudgetUnconverted = {
  currency: string;
  income: string;
  expense: string;
  amount: string;
  movement_ids: string[];
  transaction_ids: string[];
};

export type CategoryEnvelope = {
  plan_id: string;
  category_id: string;
  month: string;
  currency: string;
  assigned: string;
  activity: string;
  available: string;
  unconverted_by_currency: BudgetUnconverted[];
};

export type MonthlySummary = {
  plan_id: string;
  month: string;
  currency: string;
  ready_to_assign: string;
  assigned_total: string;
  activity_total: string;
  available_total: string;
  unconverted_by_currency: BudgetUnconverted[];
  categories: CategoryEnvelope[];
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
  payload: Pick<Plan, "name" | "reporting_currency_code"> & { budget_timezone?: string },
): Promise<Plan> {
  return request<Plan>(`/plans/${planId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getCategoryGroups(planId: string): Promise<CategoryGroup[]> {
  return request<CategoryGroup[]>(`/plans/${planId}/category-groups`);
}

export function createCategoryGroup(
  planId: string,
  groupId: string,
  name: string,
): Promise<CategoryGroup> {
  return request<CategoryGroup>(`/plans/${planId}/category-groups/${groupId}`, {
    method: "PUT",
    body: JSON.stringify({ name }),
  });
}

export function renameCategoryGroup(
  planId: string,
  groupId: string,
  name: string,
): Promise<CategoryGroup> {
  return request<CategoryGroup>(`/plans/${planId}/category-groups/${groupId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export function archiveCategoryGroup(planId: string, groupId: string): Promise<CategoryGroup> {
  return request<CategoryGroup>(`/plans/${planId}/category-groups/${groupId}/archive`, {
    method: "POST",
  });
}

export function getCategories(planId: string): Promise<Category[]> {
  return request<Category[]>(`/plans/${planId}/categories`);
}

export function createCategory(
  planId: string,
  categoryId: string,
  payload: { name: string; group_id?: string | null },
): Promise<Category> {
  return request<Category>(`/plans/${planId}/categories/${categoryId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function renameCategory(
  planId: string,
  categoryId: string,
  payload: { name?: string; group_id?: string | null },
): Promise<Category> {
  return request<Category>(`/plans/${planId}/categories/${categoryId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function archiveCategory(planId: string, categoryId: string): Promise<Category> {
  return request<Category>(`/plans/${planId}/categories/${categoryId}/archive`, {
    method: "POST",
  });
}

export function getTags(planId: string): Promise<Tag[]> {
  return request<Tag[]>(`/plans/${planId}/tags`);
}

export function createTag(planId: string, tagId: string, name: string): Promise<Tag> {
  return request<Tag>(`/plans/${planId}/tags/${tagId}`, {
    method: "PUT",
    body: JSON.stringify({ name }),
  });
}

export function renameTag(planId: string, tagId: string, name: string): Promise<Tag> {
  return request<Tag>(`/plans/${planId}/tags/${tagId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export function archiveTag(planId: string, tagId: string): Promise<Tag> {
  return request<Tag>(`/plans/${planId}/tags/${tagId}/archive`, {
    method: "POST",
  });
}

export function getTransactions(planId: string): Promise<Transaction[]> {
  return request<Transaction[]>(`/plans/${planId}/transactions`);
}

export type TransactionCreatePayload = {
  type: Transaction["type"];
  account_id: string;
  amount: string;
  currency_code: string;
  event_at: string;
  category_id?: string;
  merchant?: string;
  memo?: string;
  photo_reference?: string;
  location?: Record<string, unknown>;
  tags?: string[];
  source_metadata?: Record<string, unknown>;
  provenance?: Record<string, unknown>;
};

export function createTransaction(
  planId: string,
  transactionId: string,
  payload: TransactionCreatePayload,
): Promise<Transaction> {
  return request<Transaction>(`/plans/${planId}/transactions/${transactionId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getTransactionCorrections(
  planId: string,
  transactionId: string,
): Promise<TransactionCorrection[]> {
  return request<TransactionCorrection[]>(
    `/plans/${planId}/transactions/${transactionId}/corrections`,
  );
}

export function correctTransaction(
  planId: string,
  transactionId: string,
  correctionId: string,
  payload: Record<string, unknown>,
): Promise<TransactionCorrection> {
  return request<TransactionCorrection>(
    `/plans/${planId}/transactions/${transactionId}/corrections/${correctionId}`,
    { method: "PUT", body: JSON.stringify(payload) },
  );
}

export function getMonthlySummary(planId: string, month: string): Promise<MonthlySummary> {
  return request<MonthlySummary>(`/plans/${planId}/budget/months/${month}`);
}

export function createAssignment(
  planId: string,
  assignmentId: string,
  payload: { category_id: string; month: string; amount: string; currency_code?: string },
): Promise<unknown> {
  return request<unknown>(`/plans/${planId}/budget-assignments/${assignmentId}`, {
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
