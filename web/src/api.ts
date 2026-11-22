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
  payment_account_id?: string | null;
  goal_type?: "target_balance" | "monthly_funding" | "due_date" | null;
  goal_target?: string | null;
  goal_due_month?: string | null;
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
  type: "income" | "expense" | "transfer" | "reconciliation_adjustment";
  amount: string;
  currency_code: string;
  event_at: string;
  category_id: string | null;
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

export type Transfer = {
  id: string; plan_id: string; source_account_id: string; destination_account_id: string;
  outbound_amount: string; outbound_currency_code: string; inbound_amount: string; inbound_currency_code: string;
  event_at: string; rate: string; rate_source?: string; memo: string | null; reversal_reason: string | null;
  provenance: Record<string, unknown>; reverses_transfer_id: string | null;
  created_at: string;
  legs: { id: string; role: "outbound" | "inbound"; transaction_id: string; movement_id: string }[];
};

export type PlanActivityItem = Transaction | Transfer;

export type ReconciliationComparison = {
  id: string;
  plan_id: string;
  account_id: string;
  statement_balance: Balance;
  statement_at: string;
  derived_balance: Balance;
  discrepancy: Balance;
  policy: "block" | "warn";
  tolerance: Balance;
  requires_warning_acceptance: boolean;
  blocked: boolean;
};

export type ReconciliationSession = ReconciliationComparison & {
  warning_accepted: boolean;
  confirmed_at: string;
  adjustment_transaction_id: string | null;
  adjustment_movement_id: string | null;
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
  rollover?: string;
  cash_overspending?: string;
  credit_card_overspending?: string;
  payment_account_id?: string | null;
  payment_debt?: string;
  payment_shortfall?: string;
  goal?: BudgetGoal | null;
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
  assigned_in_future?: string;
  cash_overspending?: string;
  reconciliation_adjustments?: string;
  credit_cash_inflow?: string;
  unconverted_by_currency: BudgetUnconverted[];
  categories: CategoryEnvelope[];
};

export type BudgetGoal = {
  type: "target_balance" | "monthly_funding" | "due_date";
  target: string;
  due_month?: string | null;
  required_contribution: string;
  progress: number;
  status: "completed" | "funded" | "on_track" | "underfunded";
};

export type BudgetActionInput = {
  kind: "set_assigned" | "move" | "fund_target";
  month: string;
  category_id?: string | null;
  source_category_id?: string | null;
  amount?: string;
};

export function budgetAction(planId: string, actionId: string, payload: BudgetActionInput): Promise<unknown> {
  return request(`/plans/${planId}/budget-actions/${actionId}`, { method: "PUT", body: JSON.stringify(payload) });
}

export type GoalInput = {
  goal_type: BudgetGoal["type"] | null;
  goal_target: string | null;
  goal_due_month: string | null;
};

export function updateGoal(planId: string, categoryId: string, payload: GoalInput): Promise<Category> {
  return request<Category>(`/plans/${planId}/categories/${categoryId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
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

export function getTransactions(planId: string): Promise<PlanActivityItem[]> {
  return request<PlanActivityItem[]>(`/plans/${planId}/transactions`);
}

export function getTransfers(planId: string): Promise<Transfer[]> { return request<Transfer[]>(`/plans/${planId}/transfers`); }
export function createTransfer(planId: string, transferId: string, payload: Record<string, unknown>): Promise<Transfer> {
  return request<Transfer>(`/plans/${planId}/transfers/${transferId}`, { method: "PUT", body: JSON.stringify(payload) });
}
export function reverseTransfer(planId: string, transferId: string, reversalId: string, payload: Record<string, unknown>): Promise<Transfer> {
  return request<Transfer>(`/plans/${planId}/transfers/${transferId}/reversals/${reversalId}`, { method: "PUT", body: JSON.stringify(payload) });
}

export type TransactionCreatePayload = {
  type: "income" | "expense";
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

export type ReconciliationStatementPayload = {
  statement_balance: string;
  currency_code: string;
  statement_at: string;
};

export function previewReconciliation(
  planId: string,
  accountId: string,
  reconciliationId: string,
  payload: ReconciliationStatementPayload,
): Promise<ReconciliationComparison> {
  return request<ReconciliationComparison>(
    `/plans/${planId}/accounts/${accountId}/reconciliations/${reconciliationId}/preview`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export function confirmReconciliation(
  planId: string,
  accountId: string,
  reconciliationId: string,
  payload: ReconciliationStatementPayload & { warning_accepted: boolean },
): Promise<ReconciliationSession> {
  return request<ReconciliationSession>(
    `/plans/${planId}/accounts/${accountId}/reconciliations/${reconciliationId}`,
    { method: "PUT", body: JSON.stringify(payload) },
  );
}

export function getReconciliations(
  planId: string,
  accountId: string,
): Promise<ReconciliationSession[]> {
  return request<ReconciliationSession[]>(
    `/plans/${planId}/accounts/${accountId}/reconciliations`,
  );
}
