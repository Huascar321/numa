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
  if (response.status === 204) {
    return undefined as T;
  }
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

export type ReconciliationPreviewRequest = {
  statement_balance: string;
  statement_date: string;
};

export type ReconciliationPreview = {
  account_id: string;
  currency_code: string;
  statement_balance: string;
  statement_date: string;
  derived_balance: string;
  discrepancy: string;
  status: "balanced" | "adjusted";
};

export type ReconciliationConfirmRequest = {
  statement_balance: string;
  statement_date: string;
  memo?: string | null;
  provenance?: Record<string, unknown>;
};

export type ReconciliationSession = {
  id: string;
  plan_id: string;
  account_id: string;
  statement_balance: string;
  statement_date: string;
  derived_balance: string;
  discrepancy: string;
  currency_code: string;
  status: "balanced" | "adjusted";
  adjustment_transaction_id: string | null;
  memo: string | null;
  provenance: Record<string, unknown>;
  created_at: string;
};

export function previewReconciliation(
  planId: string,
  accountId: string,
  payload: ReconciliationPreviewRequest,
): Promise<ReconciliationPreview> {
  return request<ReconciliationPreview>(
    `/plans/${planId}/accounts/${accountId}/reconciliations/preview`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function confirmReconciliation(
  planId: string,
  accountId: string,
  reconciliationId: string,
  payload: ReconciliationConfirmRequest,
): Promise<ReconciliationSession> {
  return request<ReconciliationSession>(
    `/plans/${planId}/accounts/${accountId}/reconciliations/${reconciliationId}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
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

export type WatcherSource = {
  id: string;
  plan_id: string;
  source_type: string;
  email_address: string;
  status: "active" | "error" | "disconnected";
  history_id?: string | null;
  last_sync_at?: string | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
};

export type WatcherRawMessage = {
  id: string;
  plan_id: string;
  source_id: string;
  external_message_id: string;
  external_thread_id?: string | null;
  internal_date: string;
  history_id?: string | null;
  sender: string;
  recipient?: string | null;
  subject: string;
  snippet?: string | null;
  raw_headers: Record<string, unknown>;
  body_plain?: string | null;
  body_html?: string | null;
  mime_metadata: Record<string, unknown>;
  provenance: Record<string, unknown>;
  status: "pending" | "parsed" | "quarantined" | "ignored" | "error";
  created_at: string;
};

export type GmailAuthUrlResponse = {
  auth_url: string;
};

export type SyncResultResponse = {
  synced_count: number;
  new_messages_count: number;
  history_id?: string | null;
};

export function getGmailAuthUrl(
  planId: string,
  redirectUri: string,
): Promise<GmailAuthUrlResponse> {
  return request<GmailAuthUrlResponse>(
    `/plans/${planId}/watchers/gmail/auth-url?redirect_uri=${encodeURIComponent(redirectUri)}`,
  );
}

export function connectGmail(
  planId: string,
  code: string,
  redirectUri: string,
): Promise<WatcherSource> {
  return request<WatcherSource>(`/plans/${planId}/watchers/gmail/connect`, {
    method: "POST",
    body: JSON.stringify({ code, redirect_uri: redirectUri }),
  });
}

export function getWatcherSources(planId: string): Promise<WatcherSource[]> {
  return request<WatcherSource[]>(`/plans/${planId}/watchers/sources`);
}

export function getWatcherSource(
  planId: string,
  sourceId: string,
): Promise<WatcherSource> {
  return request<WatcherSource>(`/plans/${planId}/watchers/sources/${sourceId}`);
}

export function disconnectWatcherSource(
  planId: string,
  sourceId: string,
): Promise<WatcherSource> {
  return request<WatcherSource>(
    `/plans/${planId}/watchers/sources/${sourceId}/disconnect`,
    {
      method: "POST",
    },
  );
}

export function syncWatcherSource(
  planId: string,
  sourceId: string,
): Promise<SyncResultResponse> {
  return request<SyncResultResponse>(
    `/plans/${planId}/watchers/sources/${sourceId}/sync`,
    {
      method: "POST",
    },
  );
}

export function getWatcherMessages(
  planId: string,
  sourceId?: string,
): Promise<WatcherRawMessage[]> {
  const query = sourceId ? `?source_id=${encodeURIComponent(sourceId)}` : "";
  return request<WatcherRawMessage[]>(
    `/plans/${planId}/watchers/messages${query}`,
  );
}

export type RuleEvidenceItem = {
  rule_id: string;
  rule_name: string;
  stage: string;
  priority: number;
  result: "matched" | "skipped" | "conflict";
  conflicting_field?: string | null;
  existing_value?: unknown;
  attempted_value?: unknown;
  applied_action?: Record<string, unknown>;
  timestamp: string;
};

export type WatcherCandidate = {
  id: string;
  plan_id: string;
  raw_message_id: string;
  source_id: string;
  candidate_type: string;
  status: "pending" | "resolved" | "quarantined" | "ignored" | "rejected";
  event_at: string | null;
  notification_at?: string | null;
  reported_amount: string;
  reported_currency: string;
  settlement_amount?: string | null;
  settlement_currency?: string | null;
  merchant?: string | null;
  subject: string;
  sender: string;
  provider_uuid?: string | null;
  message_id_header?: string | null;
  quarantine_reason?: string | null;
  rule_evidence?: RuleEvidenceItem[];
  glosa?: string | null;
  raw_glosa?: string | null;
  qr_subtype?: string | null;
  account_suffix?: string | null;
  direction?: string | null;
  raw_payload: Record<string, unknown>;
  provenance: Record<string, unknown>;
  transaction_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type ResolveCandidateRequest = {
  account_id: string;
  category_id?: string | null;
  settlement_amount?: string | null;
  settlement_currency?: string | null;
  memo?: string | null;
  tags?: string[] | null;
};

export type WatcherAccountMapping = {
  id: string;
  plan_id: string;
  source_type: string;
  pattern: string;
  account_id: string;
  default_category_id?: string | null;
  auto_resolve: boolean;
  created_at: string;
  updated_at: string;
};

export type CreateAccountMappingRequest = {
  source_type?: string;
  pattern: string;
  account_id: string;
  default_category_id?: string | null;
  auto_resolve?: boolean;
};

export type ProcessCandidatesResponse = {
  processed_count: number;
  candidates_created: number;
  candidates_resolved: number;
  candidates_quarantined: number;
};

export type Rule = {
  id: string;
  plan_id: string;
  name: string;
  stage: string;
  priority: number;
  enabled: boolean;
  predicate: Record<string, unknown>;
  action: Record<string, unknown>;
  version: number;
  created_at: string;
  updated_at: string;
};

export type RuleCreate = {
  name: string;
  stage?: string;
  priority?: number;
  enabled?: boolean;
  predicate: Record<string, unknown>;
  action: Record<string, unknown>;
};

export type RuleUpdate = {
  name?: string;
  stage?: string;
  priority?: number;
  enabled?: boolean;
  predicate?: Record<string, unknown>;
  action?: Record<string, unknown>;
};

export type ReplayRulesResponse = {
  replayed_count: number;
  modified_count: number;
  quarantined_count: number;
  resolved_count: number;
};

export function getWatcherCandidates(
  planId: string,
  status?: string,
): Promise<WatcherCandidate[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<WatcherCandidate[]>(
    `/plans/${planId}/watchers/candidates${query}`,
  );
}

export function processWatcherCandidates(
  planId: string,
): Promise<ProcessCandidatesResponse> {
  return request<ProcessCandidatesResponse>(
    `/plans/${planId}/watchers/candidates/process`,
    {
      method: "POST",
    },
  );
}

export function resolveWatcherCandidate(
  planId: string,
  candidateId: string,
  payload: ResolveCandidateRequest,
): Promise<WatcherCandidate> {
  return request<WatcherCandidate>(
    `/plans/${planId}/watchers/candidates/${candidateId}/resolve`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function ignoreWatcherCandidate(
  planId: string,
  candidateId: string,
  reason?: string,
): Promise<WatcherCandidate> {
  return request<WatcherCandidate>(
    `/plans/${planId}/watchers/candidates/${candidateId}/ignore`,
    {
      method: "POST",
      body: JSON.stringify({ reason }),
    },
  );
}

export function getWatcherAccountMappings(
  planId: string,
  sourceType?: string,
): Promise<WatcherAccountMapping[]> {
  const query = sourceType ? `?source_type=${encodeURIComponent(sourceType)}` : "";
  return request<WatcherAccountMapping[]>(
    `/plans/${planId}/watchers/mappings${query}`,
  );
}

export function createWatcherAccountMapping(
  planId: string,
  payload: CreateAccountMappingRequest,
): Promise<WatcherAccountMapping> {
  return request<WatcherAccountMapping>(
    `/plans/${planId}/watchers/mappings`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function deleteWatcherAccountMapping(
  planId: string,
  mappingId: string,
): Promise<void> {
  return request<void>(
    `/plans/${planId}/watchers/mappings/${mappingId}/delete`,
    {
      method: "POST",
    },
  );
}

export function getRules(
  planId: string,
  stage?: string,
  enabled?: boolean,
): Promise<Rule[]> {
  const params = new URLSearchParams();
  if (stage) params.set("stage", stage);
  if (enabled !== undefined) params.set("enabled", String(enabled));
  const qs = params.toString() ? `?${params.toString()}` : "";
  return request<Rule[]>(`/plans/${planId}/rules${qs}`);
}

export function createRule(
  planId: string,
  payload: RuleCreate,
): Promise<Rule> {
  return request<Rule>(`/plans/${planId}/rules`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateRule(
  planId: string,
  ruleId: string,
  payload: RuleUpdate,
): Promise<Rule> {
  return request<Rule>(`/plans/${planId}/rules/${ruleId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteRule(
  planId: string,
  ruleId: string,
): Promise<void> {
  return request<void>(`/plans/${planId}/rules/${ruleId}/delete`, {
    method: "POST",
  });
}

export function replayRules(
  planId: string,
  candidateIds?: string[],
): Promise<ReplayRulesResponse> {
  return request<ReplayRulesResponse>(`/plans/${planId}/rules/replay`, {
    method: "POST",
    body: candidateIds ? JSON.stringify({ candidate_ids: candidateIds }) : undefined,
  });
}

export type StatementRow = {
  id?: string | null;
  source_row_index: number;
  event_at: string;
  transaction_number: string;
  channel?: string | null;
  description: string;
  type: "debit" | "credit";
  amount: string;
  signed_amount: string;
  running_balance: string;
  compound_identity: string;
  transaction_id?: string | null;
  match_status: string;
  card_suffix?: string | null;
  metadata?: Record<string, unknown>;
};

export type StatementDryRunRequest = {
  account_id: string;
  csv_content: string;
  filename?: string;
};

export type StatementDryRunResponse = {
  account_id: string;
  currency_code: string;
  opening_balance?: string | null;
  closing_balance?: string | null;
  current_balance?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  exported_at?: string | null;
  debit_count: number;
  credit_count: number;
  debit_sum: string;
  credit_sum: string;
  warnings: string[];
  rows: StatementRow[];
};

export type StatementCommitRequest = {
  account_id: string;
  csv_content: string;
  filename?: string;
};

export type StatementImportSummary = {
  id: string;
  plan_id: string;
  account_id: string;
  filename?: string | null;
  source_format: string;
  status: string;
  opening_balance?: string | null;
  closing_balance?: string | null;
  current_balance?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  exported_at?: string | null;
  debit_count: number;
  credit_count: number;
  debit_sum: string;
  credit_sum: string;
  currency_code: string;
  warnings: string[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type StatementImportDetail = StatementImportSummary & {
  rows: StatementRow[];
};

export function dryRunStatement(
  planId: string,
  payload: StatementDryRunRequest,
): Promise<StatementDryRunResponse> {
  return request<StatementDryRunResponse>(`/plans/${planId}/statements/dry-run`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function commitStatement(
  planId: string,
  importId: string,
  payload: StatementCommitRequest,
): Promise<StatementImportDetail> {
  return request<StatementImportDetail>(
    `/plans/${planId}/statements/${importId}/commit`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}

export function getStatementImports(
  planId: string,
  accountId?: string,
): Promise<StatementImportSummary[]> {
  const qs = accountId ? `?account_id=${encodeURIComponent(accountId)}` : "";
  return request<StatementImportSummary[]>(`/plans/${planId}/statements/imports${qs}`);
}

export function getStatementImportDetail(
  planId: string,
  importId: string,
): Promise<StatementImportDetail> {
  return request<StatementImportDetail>(
    `/plans/${planId}/statements/imports/${importId}`,
  );
}

export type CandidateSummary = {
  id: string;
  candidate_type: string;
  reported_amount: string;
  reported_currency: string;
  settlement_amount?: string | null;
  settlement_currency?: string | null;
  merchant?: string | null;
  subject: string;
  glosa?: string | null;
  account_suffix?: string | null;
  direction?: string | null;
  event_at?: string | null;
  notification_at?: string | null;
  status: string;
};

export type StatementRowSummary = {
  id: string;
  import_id: string;
  account_id: string;
  source_row_index: number;
  event_at: string;
  transaction_number: string;
  channel?: string | null;
  description: string;
  type: string;
  amount: string;
  signed_amount: string;
  match_status: string;
  card_suffix?: string | null;
};

export type TransactionSummary = {
  id: string;
  account_id: string;
  type: string;
  amount: string;
  currency_code: string;
  event_at: string;
  category_id?: string | null;
  merchant?: string | null;
  memo?: string | null;
  source: string;
};

export type TransactionMatch = {
  id: string;
  plan_id: string;
  candidate_id?: string | null;
  statement_row_id?: string | null;
  transaction_id?: string | null;
  classification: "EXACT_MATCH" | "HIGH_CONFIDENCE_MATCH" | "POSSIBLE_MATCH" | "NEW_TRANSACTION";
  status: "suggested" | "accepted" | "rejected" | "unlinked";
  confidence_score: string;
  signals: Record<string, unknown>;
  provenance: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  candidate?: CandidateSummary | null;
  statement_row?: StatementRowSummary | null;
  transaction?: TransactionSummary | null;
};

export type MatchEvaluationRequest = {
  candidate_id?: string;
  statement_row_id?: string;
  auto_link_exact?: boolean;
};

export type MatchEvaluationResponse = {
  evaluations: TransactionMatch[];
  evaluated_candidates_count: number;
  evaluated_statement_rows_count: number;
  matches_created_count: number;
};

export function evaluateMatches(
  planId: string,
  payload?: MatchEvaluationRequest,
): Promise<MatchEvaluationResponse> {
  return request<MatchEvaluationResponse>(`/plans/${planId}/matching/evaluate`, {
    method: "POST",
    body: payload ? JSON.stringify(payload) : undefined,
  });
}

export function getMatches(
  planId: string,
  status?: string,
  classification?: string,
): Promise<TransactionMatch[]> {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  if (classification) params.append("classification", classification);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return request<TransactionMatch[]>(`/plans/${planId}/matching/matches${qs}`);
}

export function getMatchDetail(
  planId: string,
  matchId: string,
): Promise<TransactionMatch> {
  return request<TransactionMatch>(`/plans/${planId}/matching/matches/${matchId}`);
}

export function acceptMatch(
  planId: string,
  matchId: string,
): Promise<TransactionMatch> {
  return request<TransactionMatch>(
    `/plans/${planId}/matching/matches/${matchId}/accept`,
    { method: "POST" },
  );
}

export function rejectMatch(
  planId: string,
  matchId: string,
  reason?: string,
): Promise<TransactionMatch> {
  return request<TransactionMatch>(
    `/plans/${planId}/matching/matches/${matchId}/reject`,
    {
      method: "POST",
      body: reason ? JSON.stringify({ reason }) : undefined,
    },
  );
}

export function unlinkMatch(
  planId: string,
  matchId: string,
  reason?: string,
): Promise<TransactionMatch> {
  return request<TransactionMatch>(
    `/plans/${planId}/matching/matches/${matchId}/unlink`,
    {
      method: "POST",
      body: reason ? JSON.stringify({ reason }) : undefined,
    },
  );
}

export type AIConfig = {
  id: string;
  plan_id: string;
  provider: string;
  model: string;
  has_api_key: boolean;
  masked_api_key?: string | null;
  is_enabled: boolean;
  base_url?: string | null;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AIConfigUpdate = {
  provider?: string;
  model?: string;
  api_key?: string;
  clear_api_key?: boolean;
  is_enabled?: boolean;
  base_url?: string;
  settings?: Record<string, unknown>;
};

export type AIModelOption = {
  id: string;
  name: string;
  provider: string;
  recommended: boolean;
  description?: string | null;
};

export type AISuggestion = {
  id: string;
  plan_id: string;
  candidate_id?: string | null;
  transaction_id?: string | null;
  suggestion_type: string;
  status: "suggested" | "accepted" | "rejected" | "quarantined";
  suggested_category_id?: string | null;
  suggested_merchant?: string | null;
  suggested_glosa?: string | null;
  suggested_tags: string[];
  confidence?: string | null;
  reasoning?: string | null;
  validation_errors?: Record<string, unknown> | Array<unknown> | null;
  provenance: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export function getAIConfig(planId: string): Promise<AIConfig> {
  return request<AIConfig>(`/plans/${planId}/ai/config`);
}

export function updateAIConfig(
  planId: string,
  payload: AIConfigUpdate,
): Promise<AIConfig> {
  return request<AIConfig>(`/plans/${planId}/ai/config`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getAIModels(
  planId: string,
  provider?: string,
): Promise<AIModelOption[]> {
  const qs = provider ? `?provider=${encodeURIComponent(provider)}` : "";
  return request<AIModelOption[]>(`/plans/${planId}/ai/models${qs}`);
}

export function generateCandidateSuggestion(
  planId: string,
  candidateId: string,
): Promise<AISuggestion> {
  return request<AISuggestion>(
    `/plans/${planId}/ai/suggest/candidate/${candidateId}`,
    { method: "POST" },
  );
}

export function generateTransactionSuggestion(
  planId: string,
  transactionId: string,
): Promise<AISuggestion> {
  return request<AISuggestion>(
    `/plans/${planId}/ai/suggest/transaction/${transactionId}`,
    { method: "POST" },
  );
}

export function getAISuggestions(
  planId: string,
  params?: {
    status?: string;
    candidate_id?: string;
    transaction_id?: string;
  },
): Promise<AISuggestion[]> {
  const q = new URLSearchParams();
  if (params?.status) q.append("status", params.status);
  if (params?.candidate_id) q.append("candidate_id", params.candidate_id);
  if (params?.transaction_id) q.append("transaction_id", params.transaction_id);
  const qs = q.toString() ? `?${q.toString()}` : "";
  return request<AISuggestion[]>(`/plans/${planId}/ai/suggestions${qs}`);
}

export function acceptAISuggestion(
  planId: string,
  suggestionId: string,
): Promise<AISuggestion> {
  return request<AISuggestion>(
    `/plans/${planId}/ai/suggestions/${suggestionId}/accept`,
    { method: "POST" },
  );
}

export function rejectAISuggestion(
  planId: string,
  suggestionId: string,
  reason?: string,
): Promise<AISuggestion> {
  return request<AISuggestion>(
    `/plans/${planId}/ai/suggestions/${suggestionId}/reject`,
    {
      method: "POST",
      body: reason ? JSON.stringify({ reason }) : undefined,
    },
  );
}

export type AutomationSuggestionStatus =
  | "suggested"
  | "accepted"
  | "rejected"
  | "dismissed";

export type AutomationSuggestion = {
  id: string;
  plan_id: string;
  suggestion_type: string;
  status: AutomationSuggestionStatus;
  title: string;
  description?: string | null;
  rule_stage: string;
  suggested_priority: number;
  predicate: Record<string, unknown>;
  action: Record<string, unknown>;
  evidence: Record<string, unknown>;
  confidence?: string | number | null;
  source: string;
  created_rule_id?: string | null;
  decided_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type DiscoverAutomationSuggestionsResponse = {
  discovered_count: number;
  created_count: number;
  suggestions: AutomationSuggestion[];
};

export type AutomationSuggestionAcceptPayload = {
  name?: string;
  priority?: number;
  predicate?: Record<string, unknown>;
  action?: Record<string, unknown>;
};

export type AutomationSuggestionRejectPayload = {
  reason?: string;
};

export function discoverAutomationSuggestions(
  planId: string,
): Promise<DiscoverAutomationSuggestionsResponse> {
  return request<DiscoverAutomationSuggestionsResponse>(
    `/plans/${planId}/automation/suggestions/discover`,
    { method: "POST" },
  );
}

export function getAutomationSuggestions(
  planId: string,
  params?: {
    status?: string;
    source?: string;
  },
): Promise<AutomationSuggestion[]> {
  const q = new URLSearchParams();
  if (params?.status) q.append("status", params.status);
  if (params?.source) q.append("source", params.source);
  const qs = q.toString() ? `?${q.toString()}` : "";
  return request<AutomationSuggestion[]>(
    `/plans/${planId}/automation/suggestions${qs}`,
  );
}

export function getAutomationSuggestion(
  planId: string,
  suggestionId: string,
): Promise<AutomationSuggestion> {
  return request<AutomationSuggestion>(
    `/plans/${planId}/automation/suggestions/${suggestionId}`,
  );
}

export function acceptAutomationSuggestion(
  planId: string,
  suggestionId: string,
  payload?: AutomationSuggestionAcceptPayload,
): Promise<AutomationSuggestion> {
  return request<AutomationSuggestion>(
    `/plans/${planId}/automation/suggestions/${suggestionId}/accept`,
    {
      method: "POST",
      body: payload ? JSON.stringify(payload) : undefined,
    },
  );
}

export function rejectAutomationSuggestion(
  planId: string,
  suggestionId: string,
  reason?: string,
): Promise<AutomationSuggestion> {
  return request<AutomationSuggestion>(
    `/plans/${planId}/automation/suggestions/${suggestionId}/reject`,
    {
      method: "POST",
      body: reason ? JSON.stringify({ reason }) : undefined,
    },
  );
}

export function dismissAutomationSuggestion(
  planId: string,
  suggestionId: string,
): Promise<AutomationSuggestion> {
  return request<AutomationSuggestion>(
    `/plans/${planId}/automation/suggestions/${suggestionId}/dismiss`,
    { method: "POST" },
  );
}

export type UnconvertedAmountItem = {
  currency_code: string;
  amount: string;
  transaction_count: number;
};

export type UnconvertedCurrencySummary = {
  currency_code: string;
  total_income: string;
  total_expenses: string;
  net_amount: string;
  transaction_count: number;
};

export type AnalyticsSummary = {
  plan_id: string;
  reporting_currency_code: string;
  period_start: string;
  period_end: string;
  total_income: string;
  total_expenses: string;
  net_cashflow: string;
  savings_rate: string;
  transaction_count: number;
  transfers_count: number;
  transfers_excluded_notice: string;
  unconverted_totals: UnconvertedCurrencySummary[];
};

export type CategoryAnalyticsItem = {
  category_id: string | null;
  category_name: string;
  group_id: string | null;
  group_name: string | null;
  amount: string;
  percentage: string;
  transaction_count: number;
  unconverted_by_currency: UnconvertedAmountItem[];
};

export type CategoryGroupAnalyticsItem = {
  group_id: string | null;
  group_name: string;
  amount: string;
  percentage: string;
  transaction_count: number;
  categories: CategoryAnalyticsItem[];
};

export type CategoryBreakdown = {
  plan_id: string;
  reporting_currency_code: string;
  period_start: string;
  period_end: string;
  type: "expense" | "income" | "all";
  total_amount: string;
  categories: CategoryAnalyticsItem[];
  groups: CategoryGroupAnalyticsItem[];
  unconverted_totals: UnconvertedCurrencySummary[];
};

export type MerchantRankingItem = {
  merchant: string;
  total_amount: string;
  percentage: string;
  transaction_count: number;
  average_amount: string;
  unconverted_by_currency: UnconvertedAmountItem[];
};

export type MerchantRankings = {
  plan_id: string;
  reporting_currency_code: string;
  period_start: string;
  period_end: string;
  total_expense_amount: string;
  merchants: MerchantRankingItem[];
  unconverted_totals: UnconvertedCurrencySummary[];
};

export type TagAnalyticsItem = {
  tag_id: string;
  tag_name: string;
  amount: string;
  percentage: string;
  transaction_count: number;
  unconverted_by_currency: UnconvertedAmountItem[];
};

export type TagBreakdown = {
  plan_id: string;
  reporting_currency_code: string;
  period_start: string;
  period_end: string;
  type: "expense" | "income" | "all";
  total_tagged_amount: string;
  tags: TagAnalyticsItem[];
  untagged_amount: string;
  untagged_transaction_count: number;
  unconverted_totals: UnconvertedCurrencySummary[];
};

export type CashflowTrendPoint = {
  bucket_key: string;
  bucket_start: string;
  bucket_end: string;
  income: string;
  expense: string;
  net: string;
  cumulative_net: string;
  transaction_count: number;
  unconverted_by_currency: UnconvertedCurrencySummary[];
};

export type CashflowTrends = {
  plan_id: string;
  reporting_currency_code: string;
  interval: "day" | "week" | "month";
  period_start: string;
  period_end: string;
  points: CashflowTrendPoint[];
};

export type HeatmapCell = {
  day_of_week: number;
  day_name: string;
  hour_of_day: number;
  transaction_count: number;
  total_amount: string;
};

export type DailyActivityCell = {
  date: string;
  transaction_count: number;
  income: string;
  expense: string;
  total_amount: string;
};

export type LocationAnalyticsPoint = {
  latitude: number | null;
  longitude: number | null;
  label: string | null;
  merchant: string | null;
  amount: string;
  currency_code: string;
  transaction_count: number;
};

export type ActivityHeatmap = {
  plan_id: string;
  reporting_currency_code: string;
  period_start: string;
  period_end: string;
  day_hour_matrix: HeatmapCell[];
  daily_activity: DailyActivityCell[];
  location_clusters: LocationAnalyticsPoint[] | null;
};

export type CategoryGoalAnalyticsItem = {
  category_id: string;
  category_name: string;
  group_name: string | null;
  goal_type: string;
  goal_target: string;
  goal_due_month: string | null;
  current_progress_amount: string;
  target_amount: string;
  progress_percentage: string;
  remaining_amount: string;
  status: string;
};

export type GoalsAnalytics = {
  plan_id: string;
  reporting_currency_code: string;
  as_of_month: string;
  goals: CategoryGoalAnalyticsItem[];
};

export function getAnalyticsSummary(
  planId: string,
  params?: { month?: string; start_date?: string; end_date?: string },
): Promise<AnalyticsSummary> {
  const q = new URLSearchParams();
  if (params?.month) q.append("month", params.month);
  if (params?.start_date) q.append("start_date", params.start_date);
  if (params?.end_date) q.append("end_date", params.end_date);
  const qs = q.toString() ? `?${q.toString()}` : "";
  return request<AnalyticsSummary>(`/plans/${planId}/analytics/summary${qs}`);
}

export function getCategoryBreakdown(
  planId: string,
  params?: {
    month?: string;
    start_date?: string;
    end_date?: string;
    type?: "expense" | "income" | "all";
  },
): Promise<CategoryBreakdown> {
  const q = new URLSearchParams();
  if (params?.month) q.append("month", params.month);
  if (params?.start_date) q.append("start_date", params.start_date);
  if (params?.end_date) q.append("end_date", params.end_date);
  if (params?.type) q.append("type", params.type);
  const qs = q.toString() ? `?${q.toString()}` : "";
  return request<CategoryBreakdown>(
    `/plans/${planId}/analytics/categories${qs}`,
  );
}

export function getMerchantRankings(
  planId: string,
  params?: {
    month?: string;
    start_date?: string;
    end_date?: string;
    limit?: number;
  },
): Promise<MerchantRankings> {
  const q = new URLSearchParams();
  if (params?.month) q.append("month", params.month);
  if (params?.start_date) q.append("start_date", params.start_date);
  if (params?.end_date) q.append("end_date", params.end_date);
  if (params?.limit !== undefined) q.append("limit", params.limit.toString());
  const qs = q.toString() ? `?${q.toString()}` : "";
  return request<MerchantRankings>(`/plans/${planId}/analytics/merchants${qs}`);
}

export function getTagBreakdown(
  planId: string,
  params?: {
    month?: string;
    start_date?: string;
    end_date?: string;
    type?: "expense" | "income" | "all";
  },
): Promise<TagBreakdown> {
  const q = new URLSearchParams();
  if (params?.month) q.append("month", params.month);
  if (params?.start_date) q.append("start_date", params.start_date);
  if (params?.end_date) q.append("end_date", params.end_date);
  if (params?.type) q.append("type", params.type);
  const qs = q.toString() ? `?${q.toString()}` : "";
  return request<TagBreakdown>(`/plans/${planId}/analytics/tags${qs}`);
}

export function getCashflowTrends(
  planId: string,
  params?: {
    month?: string;
    start_date?: string;
    end_date?: string;
    interval?: "day" | "week" | "month";
  },
): Promise<CashflowTrends> {
  const q = new URLSearchParams();
  if (params?.month) q.append("month", params.month);
  if (params?.start_date) q.append("start_date", params.start_date);
  if (params?.end_date) q.append("end_date", params.end_date);
  if (params?.interval) q.append("interval", params.interval);
  const qs = q.toString() ? `?${q.toString()}` : "";
  return request<CashflowTrends>(`/plans/${planId}/analytics/trends${qs}`);
}

export function getActivityHeatmap(
  planId: string,
  params?: {
    month?: string;
    start_date?: string;
    end_date?: string;
    include_locations?: boolean;
  },
): Promise<ActivityHeatmap> {
  const q = new URLSearchParams();
  if (params?.month) q.append("month", params.month);
  if (params?.start_date) q.append("start_date", params.start_date);
  if (params?.end_date) q.append("end_date", params.end_date);
  if (params?.include_locations !== undefined)
    q.append("include_locations", String(params.include_locations));
  const qs = q.toString() ? `?${q.toString()}` : "";
  return request<ActivityHeatmap>(`/plans/${planId}/analytics/heatmap${qs}`);
}

export function getGoalsAnalytics(
  planId: string,
  params?: { as_of_month?: string },
): Promise<GoalsAnalytics> {
  const q = new URLSearchParams();
  if (params?.as_of_month) q.append("as_of_month", params.as_of_month);
  const qs = q.toString() ? `?${q.toString()}` : "";
  return request<GoalsAnalytics>(`/plans/${planId}/analytics/goals${qs}`);
}

export type ExchangeRateQuote = {
  id: string;
  plan_id: string;
  base_currency: string;
  quote_currency: string;
  side: "BUY_USDT" | "SELL_USDT";
  bob_amount: string;
  usdt_amount: string;
  rate: string;
  payment_method: string | null;
  fee_amount: string | null;
  min_limit: string | null;
  max_limit: string | null;
  source: string;
  offer_context: Record<string, unknown>;
  observed_at: string;
  created_at: string;
  updated_at: string;
  is_stale: boolean;
  freshness: "fresh" | "stale";
};

export type QuoteCreate = {
  side: "BUY_USDT" | "SELL_USDT";
  bob_amount: string;
  usdt_amount: string;
  base_currency?: string;
  quote_currency?: string;
  rate?: string;
  payment_method?: string | null;
  fee_amount?: string | null;
  min_limit?: string | null;
  max_limit?: string | null;
  source?: string;
  offer_context?: Record<string, unknown>;
  observed_at?: string;
};

export type LatestQuotes = {
  buy_quote: ExchangeRateQuote | null;
  sell_quote: ExchangeRateQuote | null;
  has_fresh_quote: boolean;
  has_quote: boolean;
  is_stale: boolean;
  staleness_threshold_hours: number;
};

export type ConvertRequest = {
  from_currency: string;
  to_currency: string;
  amount: string;
  side?: "BUY_USDT" | "SELL_USDT";
  quote_id?: string;
  custom_rate?: string;
};

export type ConvertResponse = {
  from_currency: string;
  to_currency: string;
  from_amount: string;
  to_amount: string;
  rate_used: string;
  rate_source: string;
  quote_id: string | null;
  rate_observed_at: string | null;
  is_stale: boolean;
  formula: string;
  provenance: Record<string, unknown>;
};

export type FXProvider = {
  id: string;
  name: string;
  status: "available" | "reference_only" | "unverified_optional" | "unavailable";
  is_primary: boolean;
  description: string;
  last_checked_at: string | null;
  notes: string | null;
};

export function createQuote(
  planId: string,
  payload: QuoteCreate,
): Promise<ExchangeRateQuote> {
  return request<ExchangeRateQuote>(`/plans/${planId}/fx/quotes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getQuotes(
  planId: string,
  params?: {
    side?: string;
    source?: string;
    limit?: number;
  },
): Promise<ExchangeRateQuote[]> {
  const q = new URLSearchParams();
  if (params?.side) q.append("side", params.side);
  if (params?.source) q.append("source", params.source);
  if (params?.limit !== undefined) q.append("limit", params.limit.toString());
  const qs = q.toString() ? `?${q.toString()}` : "";
  return request<ExchangeRateQuote[]>(`/plans/${planId}/fx/quotes${qs}`);
}

export function getLatestQuote(
  planId: string,
  maxAgeHours?: number,
): Promise<LatestQuotes> {
  const q = new URLSearchParams();
  if (maxAgeHours !== undefined)
    q.append("max_age_hours", maxAgeHours.toString());
  const qs = q.toString() ? `?${q.toString()}` : "";
  return request<LatestQuotes>(`/plans/${planId}/fx/quotes/latest${qs}`);
}

export function convertCurrency(
  planId: string,
  payload: ConvertRequest,
): Promise<ConvertResponse> {
  return request<ConvertResponse>(`/plans/${planId}/fx/convert`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getFXProviders(planId: string): Promise<FXProvider[]> {
  return request<FXProvider[]>(`/plans/${planId}/fx/providers`);
}
