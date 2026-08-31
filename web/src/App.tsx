import { FormEvent, useEffect, useState } from "react";
import {
  Link,
  Navigate,
  Route,
  Routes,
  useNavigate,
  useParams,
} from "react-router";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  ACCOUNT_TYPES,
  Account,
  createAccount,
  createPlan,
  archiveAccount,
  getAccounts,
  getCurrencies,
  getPlan,
  getPlans,
  newClientId,
  renameAccount,
  renamePlan,
  Category,
  CategoryGroup,
  Tag,
  Transaction,
  createAssignment,
  createCategory,
  createCategoryGroup,
  createTag,
  createTransaction,
  getCategories,
  getCategoryGroups,
  getMonthlySummary,
  getTags,
  getTransactions,
  archiveCategory,
  archiveCategoryGroup,
  archiveTag,
  renameCategory,
  renameCategoryGroup,
  renameTag,
  correctTransaction,
  getTransactionCorrections,
  Transfer,
  getTransfers,
  createTransfer,
  reverseTransfer,
  ReconciliationPreview,
  ReconciliationSession,
  previewReconciliation,
  confirmReconciliation,
  getReconciliations,
  WatcherSource,
  WatcherRawMessage,
  WatcherCandidate,
  WatcherAccountMapping,
  Rule,
  RuleCreate,
  ReplayRulesResponse,
  getGmailAuthUrl,
  connectGmail,
  getWatcherSources,
  disconnectWatcherSource,
  syncWatcherSource,
  getWatcherMessages,
  getWatcherCandidates,
  processWatcherCandidates,
  resolveWatcherCandidate,
  ignoreWatcherCandidate,
  getWatcherAccountMappings,
  createWatcherAccountMapping,
  deleteWatcherAccountMapping,
  getRules,
  createRule,
  updateRule,
  deleteRule,
  replayRules,
  StatementRow,
  StatementDryRunResponse,
  StatementImportSummary,
  StatementImportDetail,
  dryRunStatement,
  commitStatement,
  getStatementImports,
  getStatementImportDetail,
  TransactionMatch,
  evaluateMatches,
  getMatches,
  acceptMatch,
  rejectMatch,
  unlinkMatch,
  AIConfig,
  AIConfigUpdate,
  AIModelOption,
  AISuggestion,
  getAIConfig,
  updateAIConfig,
  getAIModels,
  generateCandidateSuggestion,
  generateTransactionSuggestion,
  getAISuggestions,
  acceptAISuggestion,
  rejectAISuggestion,
  AutomationSuggestion,
  discoverAutomationSuggestions,
  getAutomationSuggestions,
  acceptAutomationSuggestion,
  dismissAutomationSuggestion,
  rejectAutomationSuggestion,
  getAnalyticsSummary,
  getCategoryBreakdown,
  getMerchantRankings,
  getTagBreakdown,
  getCashflowTrends,
  getActivityHeatmap,
  getGoalsAnalytics,
  ExchangeRateQuote,
  QuoteCreate,
  LatestQuotes,
  ConvertRequest,
  ConvertResponse,
  FXProvider,
  createQuote,
  getQuotes,
  getLatestQuote,
  convertCurrency,
  getFXProviders,
} from "./api";

function ErrorMessage({ message }: { message: string }) {
  return <p role="alert" className="error">{message}</p>;
}

function useCurrencies() {
  return useQuery({
    queryKey: ["currencies"],
    queryFn: getCurrencies,
    staleTime: 60_000,
  });
}

function PlanScreen() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const plans = useQuery({ queryKey: ["plans"], queryFn: getPlans });
  const currencies = useCurrencies();
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("BOB");
  const [timezone, setTimezone] = useState("America/La_Paz");
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const createMutation = useMutation({
    mutationFn: () => createPlan(newClientId(), {
      name,
      reporting_currency_code: currency,
      budget_timezone: timezone,
    }),
    onSuccess: async (plan) => {
      await queryClient.invalidateQueries({ queryKey: ["plans"] });
      setName("");
      navigate(`/plans/${plan.id}/accounts`);
    },
  });

  const renameMutation = useMutation({
    mutationFn: ({ planId, nextName }: { planId: string; nextName: string }) =>
      renamePlan(planId, nextName),
    onSuccess: async (plan) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["plans"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", plan.id] }),
      ]);
      setRenameId(null);
    },
  });

  function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    createMutation.mutate();
  }

  function submitRename(event: FormEvent<HTMLFormElement>, planId: string) {
    event.preventDefault();
    renameMutation.mutate({ planId, nextName: renameValue });
  }

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Numa workspace</p>
          <h1>Plans</h1>
          <p>Select an independent Plan before managing its Accounts.</p>
        </div>
      </header>

      <section className="panel" aria-labelledby="create-plan-heading">
        <h2 id="create-plan-heading">Create a Plan</h2>
        <form onSubmit={submitCreate} className="form-grid">
          <label>
            Name
            <input
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Personal finances"
            />
          </label>
          <label>
            Reporting currency
            <select
              value={currency}
              onChange={(event) => setCurrency(event.target.value)}
              disabled={currencies.isPending}
            >
              {(currencies.data ?? []).map((item) => (
                <option key={item.code} value={item.code}>{item.code}</option>
              ))}
            </select>
          </label>
          <label>
            Budget timezone (IANA)
            <input value={timezone} onChange={(event) => setTimezone(event.target.value)} required />
          </label>
          <button type="submit" disabled={createMutation.isPending || !name.trim()}>
            {createMutation.isPending ? "Creating…" : "Create Plan"}
          </button>
        </form>
        {currencies.isError && <ErrorMessage message="Currencies could not be loaded." />}
        {createMutation.isError && (
          <ErrorMessage message={createMutation.error.message} />
        )}
      </section>

      <section className="panel" aria-labelledby="plans-heading">
        <h2 id="plans-heading">Your Plans</h2>
        {plans.isPending && <p>Loading Plans…</p>}
        {plans.isError && <ErrorMessage message="Plans could not be loaded." />}
        {plans.data?.length === 0 && <p>No Plans yet.</p>}
        <div className="card-list">
          {plans.data?.map((plan) => (
            <article className="card" key={plan.id}>
              <div>
                <h3>{plan.name}</h3>
                <p>Reporting currency: <strong>{plan.reporting_currency_code}</strong></p>
              </div>
              <div className="card-actions">
                <Link className="button" to={`/plans/${plan.id}/accounts`}>Manage Accounts</Link>
                <button
                  type="button"
                  onClick={() => {
                    setRenameId(plan.id);
                    setRenameValue(plan.name);
                  }}
                >
                  Rename
                </button>
              </div>
              {renameId === plan.id && (
                <form onSubmit={(event) => submitRename(event, plan.id)} className="inline-form">
                  <label>
                    New name
                    <input
                      required
                      value={renameValue}
                      onChange={(event) => setRenameValue(event.target.value)}
                    />
                  </label>
                  <button type="submit" disabled={renameMutation.isPending}>Save</button>
                  <button type="button" onClick={() => setRenameId(null)}>Cancel</button>
                </form>
              )}
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}

function AccountCard({ account, planId }: { account: Account; planId: string }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(account.name);
  const [reconciling, setReconciling] = useState(false);
  const [importingStatement, setImportingStatement] = useState(false);

  const invalidateAccounts = () => queryClient.invalidateQueries({
    queryKey: ["plans", planId, "accounts"],
  });
  const renameMutation = useMutation({
    mutationFn: () => renameAccount(planId, account.id, name),
    onSuccess: async () => {
      await invalidateAccounts();
      setEditing(false);
    },
  });
  const archiveMutation = useMutation({
    mutationFn: () => archiveAccount(planId, account.id),
    onSuccess: invalidateAccounts,
  });

  return (
    <article className="card account-card" data-testid={`account-${account.id}`}>
      <div className="account-heading">
        <div>
          <h3>{account.name}</h3>
          <p>{account.account_type} · {account.currency_code}</p>
        </div>
        <span className={`status status-${account.status}`}>{account.status}</span>
      </div>
      <p className="balance">
        Balance <strong>{account.balance.amount} {account.balance.currency}</strong>
      </p>
      {account.status === "active" && (
        <div className="card-actions">
          <button type="button" onClick={() => setReconciling(!reconciling)}>
            {reconciling ? "Close Reconciliation" : "Reconcile"}
          </button>
          <button
            type="button"
            onClick={() => setImportingStatement(!importingStatement)}
          >
            {importingStatement ? "Close Import" : "Import Statement"}
          </button>
          <button type="button" onClick={() => setEditing(true)}>Rename</button>
          <button
            type="button"
            onClick={() => archiveMutation.mutate()}
            disabled={archiveMutation.isPending}
          >
            {archiveMutation.isPending ? "Archiving…" : "Archive"}
          </button>
        </div>
      )}
      {editing && account.status === "active" && (
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            renameMutation.mutate();
          }}
        >
          <label>
            New name
            <input value={name} onChange={(event) => setName(event.target.value)} required />
          </label>
          <button type="submit" disabled={renameMutation.isPending}>Save</button>
          <button type="button" onClick={() => setEditing(false)}>Cancel</button>
        </form>
      )}
      {renameMutation.isError && <ErrorMessage message={renameMutation.error.message} />}
      {archiveMutation.isError && <ErrorMessage message={archiveMutation.error.message} />}
      {reconciling && account.status === "active" && (
        <AccountReconciliationPanel
          planId={planId}
          account={account}
          onClose={() => setReconciling(false)}
        />
      )}
      {importingStatement && account.status === "active" && (
        <AccountStatementImportPanel
          planId={planId}
          account={account}
          onClose={() => setImportingStatement(false)}
        />
      )}
    </article>
  );
}

function AccountReconciliationPanel({
  planId,
  account,
  onClose,
}: {
  planId: string;
  account: Account;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [statementBalance, setStatementBalance] = useState("");
  const [statementDate, setStatementDate] = useState(
    new Date().toISOString().slice(0, 16)
  );
  const [memo, setMemo] = useState("");
  const [preview, setPreview] = useState<ReconciliationPreview | null>(null);

  const historyQuery = useQuery({
    queryKey: ["plans", planId, "accounts", account.id, "reconciliations"],
    queryFn: () => getReconciliations(planId, account.id),
  });

  const previewMutation = useMutation({
    mutationFn: () =>
      previewReconciliation(planId, account.id, {
        statement_balance: statementBalance,
        statement_date: new Date(statementDate).toISOString(),
      }),
    onSuccess: (data) => {
      setPreview(data);
    },
  });

  const confirmMutation = useMutation({
    mutationFn: () => {
      if (!preview) throw new Error("Preview required before confirmation.");
      return confirmReconciliation(planId, account.id, newClientId(), {
        statement_balance: preview.statement_balance,
        statement_date: preview.statement_date,
        memo: memo || undefined,
      });
    },
    onSuccess: async () => {
      setPreview(null);
      setStatementBalance("");
      setMemo("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "budget"] }),
        queryClient.invalidateQueries({
          queryKey: ["plans", planId, "accounts", account.id, "reconciliations"],
        }),
      ]);
    },
  });

  return (
    <div className="reconciliation-panel" data-testid={`reconciliation-${account.id}`}>
      <h4>Reconcile {account.name}</h4>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          previewMutation.mutate();
        }}
        className="form-grid"
      >
        <label>
          Statement balance
          <input
            required
            inputMode="decimal"
            value={statementBalance}
            onChange={(event) => {
              setStatementBalance(event.target.value);
              setPreview(null);
            }}
            placeholder="0.00"
          />
        </label>
        <label>
          Statement date
          <input
            type="datetime-local"
            required
            value={statementDate}
            onChange={(event) => {
              setStatementDate(event.target.value);
              setPreview(null);
            }}
          />
        </label>
        <label>
          Memo (optional)
          <input
            value={memo}
            onChange={(event) => setMemo(event.target.value)}
            placeholder="Monthly bank statement"
          />
        </label>
        <div className="card-actions">
          <button
            type="submit"
            disabled={previewMutation.isPending || !statementBalance.trim()}
          >
            {previewMutation.isPending ? "Calculating…" : "Preview Reconciliation"}
          </button>
          <button type="button" onClick={onClose}>
            Close
          </button>
        </div>
      </form>
      {previewMutation.isError && (
        <ErrorMessage message={previewMutation.error.message} />
      )}

      {preview && (
        <div className="preview-results" data-testid="reconciliation-preview">
          <h5>Preview Summary</h5>
          <p>
            Statement balance: <strong>{preview.statement_balance} {preview.currency_code}</strong>
          </p>
          <p>
            Derived balance: <strong>{preview.derived_balance} {preview.currency_code}</strong>
          </p>
          <p>
            Discrepancy: <strong>{preview.discrepancy} {preview.currency_code}</strong>
          </p>
          <p>
            Status: <span className={`status status-${preview.status}`}>{preview.status}</span>
          </p>
          {preview.status === "adjusted" && (
            <p className="field-help">
              An adjustment of {preview.discrepancy} {preview.currency_code} will be posted to Pendientes.
            </p>
          )}
          <button
            type="button"
            disabled={confirmMutation.isPending}
            onClick={() => confirmMutation.mutate()}
          >
            {confirmMutation.isPending
              ? "Confirming…"
              : preview.status === "balanced"
              ? "Confirm balance"
              : "Confirm & post adjustment"}
          </button>
          {confirmMutation.isError && (
            <ErrorMessage message={confirmMutation.error.message} />
          )}
        </div>
      )}

      <div className="reconciliation-history">
        <h5>Reconciliation History</h5>
        {historyQuery.isPending && <p>Loading history…</p>}
        {historyQuery.isError && (
          <ErrorMessage message={historyQuery.error.message || "Could not load history."} />
        )}
        {historyQuery.data?.length === 0 && <p>No previous reconciliations.</p>}
        <div className="card-list">
          {historyQuery.data?.map((session) => (
            <article className="card" key={session.id}>
              <p>
                <strong>{session.status}</strong> · {session.statement_date}
              </p>
              <p>
                Statement {session.statement_balance} {session.currency_code} vs Derived {session.derived_balance} {session.currency_code}
              </p>
              <p>
                Discrepancy: {session.discrepancy} {session.currency_code}
              </p>
              {session.memo && <p>Memo: {session.memo}</p>}
              {session.adjustment_transaction_id && (
                <p>Adjustment Transaction: {session.adjustment_transaction_id}</p>
              )}
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}

function AccountStatementImportPanel({
  planId,
  account,
  onClose,
}: {
  planId: string;
  account: Account;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [csvContent, setCsvContent] = useState("");
  const [fileName, setFileName] = useState("");
  const [preview, setPreview] = useState<StatementDryRunResponse | null>(null);
  const [selectedImportId, setSelectedImportId] = useState<string | null>(null);

  const historyQuery = useQuery({
    queryKey: ["plans", planId, "accounts", account.id, "statements"],
    queryFn: () => getStatementImports(planId, account.id),
  });

  const detailQuery = useQuery({
    queryKey: ["plans", planId, "statements", selectedImportId],
    queryFn: () => (selectedImportId ? getStatementImportDetail(planId, selectedImportId) : null),
    enabled: Boolean(selectedImportId),
  });

  const dryRunMutation = useMutation({
    mutationFn: () =>
      dryRunStatement(planId, {
        account_id: account.id,
        csv_content: csvContent,
        filename: fileName || undefined,
      }),
    onSuccess: (data) => {
      setPreview(data);
    },
  });

  const commitMutation = useMutation({
    mutationFn: () => {
      if (!csvContent) throw new Error("CSV content is required.");
      return commitStatement(planId, newClientId(), {
        account_id: account.id,
        csv_content: csvContent,
        filename: fileName || undefined,
      });
    },
    onSuccess: async () => {
      setPreview(null);
      setCsvContent("");
      setFileName("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "budget"] }),
        queryClient.invalidateQueries({
          queryKey: ["plans", planId, "accounts", account.id, "statements"],
        }),
      ]);
    },
  });

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = String(e.target?.result ?? "");
      setCsvContent(text);
      setPreview(null);
    };
    reader.readAsText(file);
  }

  return (
    <div className="statement-import-panel" data-testid={`statement-import-${account.id}`}>
      <h4>Import Statement for {account.name}</h4>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          dryRunMutation.mutate();
        }}
        className="form-grid"
      >
        <label>
          Statement CSV File
          <input
            type="file"
            accept=".csv,text/csv,text/plain"
            onChange={handleFileChange}
            data-testid="statement-file-input"
          />
        </label>
        {fileName && <p className="field-help">Selected: <strong>{fileName}</strong></p>}
        <label>
          Or Paste CSV Content
          <textarea
            rows={4}
            value={csvContent}
            onChange={(e) => {
              setCsvContent(e.target.value);
              setPreview(null);
            }}
            placeholder="Paste Banco Ganadero statement CSV..."
            data-testid="statement-csv-textarea"
          />
        </label>
        <div className="card-actions">
          <button
            type="submit"
            disabled={dryRunMutation.isPending || !csvContent.trim()}
            data-testid="dry-run-button"
          >
            {dryRunMutation.isPending ? "Analyzing…" : "Preview Statement (Dry Run)"}
          </button>
          <button type="button" onClick={onClose}>
            Close
          </button>
        </div>
      </form>
      {dryRunMutation.isError && (
        <ErrorMessage message={dryRunMutation.error.message} />
      )}

      {preview && (
        <div className="statement-preview" data-testid="statement-dry-run-preview">
          <h5>Statement Preview</h5>
          <div className="preview-summary-grid">
            <p>Opening Balance: <strong>{preview.opening_balance ?? "N/A"} {preview.currency_code}</strong></p>
            <p>Period Closing Balance: <strong>{preview.closing_balance ?? "N/A"} {preview.currency_code}</strong></p>
            <p>As-of Current Balance: <strong>{preview.current_balance ?? "N/A"} {preview.currency_code}</strong></p>
            <p>Debits: <strong>{preview.debit_count} ({preview.debit_sum} {preview.currency_code})</strong></p>
            <p>Credits: <strong>{preview.credit_count} ({preview.credit_sum} {preview.currency_code})</strong></p>
          </div>
          {preview.warnings.length > 0 && (
            <div className="warnings-box" data-testid="statement-warnings">
              <h6>Validation Notices / Warnings</h6>
              <ul>
                {preview.warnings.map((w, idx) => (
                  <li key={idx} className="warning-item">{w}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="table-responsive">
            <table className="statement-rows-table" data-testid="statement-rows-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Date & Time</th>
                  <th>Trans #</th>
                  <th>Description</th>
                  <th>Type</th>
                  <th>Amount</th>
                  <th>Balance</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row) => (
                  <tr key={row.source_row_index} data-testid={`statement-row-${row.source_row_index}`}>
                    <td>{row.source_row_index + 1}</td>
                    <td>{row.event_at}</td>
                    <td>{row.transaction_number}</td>
                    <td>
                      {row.description}
                      {row.card_suffix && <span className="tag">Tarj: {row.card_suffix}</span>}
                    </td>
                    <td><span className={`status status-${row.type}`}>{row.type}</span></td>
                    <td>{row.signed_amount}</td>
                    <td>{row.running_balance}</td>
                    <td><span className={`status status-${row.match_status}`}>{row.match_status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card-actions" style={{ marginTop: "1rem" }}>
            <button
              type="button"
              disabled={commitMutation.isPending}
              onClick={() => commitMutation.mutate()}
              data-testid="commit-statement-button"
            >
              {commitMutation.isPending ? "Importing & Posting…" : "Commit Statement Import"}
            </button>
          </div>
          {commitMutation.isError && (
            <ErrorMessage message={commitMutation.error.message} />
          )}
        </div>
      )}

      <div className="statement-history">
        <h5>Past Statement Imports</h5>
        {historyQuery.isPending && <p>Loading statement imports…</p>}
        {historyQuery.isError && (
          <ErrorMessage message={historyQuery.error.message || "Could not load statement imports."} />
        )}
        {historyQuery.data?.length === 0 && <p>No previous statement imports.</p>}
        <div className="card-list">
          {historyQuery.data?.map((imp) => (
            <article className="card" key={imp.id} data-testid={`import-${imp.id}`}>
              <div className="account-heading">
                <strong>{imp.filename || "Banco Ganadero CSV"}</strong>
                <span className={`status status-${imp.status}`}>{imp.status}</span>
              </div>
              <p>
                Period: {imp.period_start ? imp.period_start.slice(0, 10) : "N/A"} to{" "}
                {imp.period_end ? imp.period_end.slice(0, 10) : "N/A"}
              </p>
              <p>
                Debits: {imp.debit_count} ({imp.debit_sum} {imp.currency_code}) · Credits: {imp.credit_count} ({imp.credit_sum} {imp.currency_code})
              </p>
              <p>
                Opening: {imp.opening_balance} vs Closing: {imp.closing_balance} {imp.currency_code}
              </p>
              <button
                type="button"
                onClick={() =>
                  setSelectedImportId(selectedImportId === imp.id ? null : imp.id)
                }
              >
                {selectedImportId === imp.id ? "Hide Details" : "View Details"}
              </button>
              {selectedImportId === imp.id && detailQuery.data && (
                <div className="import-detail-rows" data-testid="import-detail-rows">
                  <p>Imported Rows ({detailQuery.data.rows.length}):</p>
                  <ul>
                    {detailQuery.data.rows.map((r) => (
                      <li key={r.source_row_index}>
                        Row {r.source_row_index + 1}: {r.event_at} - {r.description} ({r.signed_amount} {imp.currency_code}) [{r.match_status}]
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}

function AccountsScreen() {
  const { planId } = useParams<{ planId: string }>();
  const queryClient = useQueryClient();
  const currencies = useCurrencies();
  const plan = useQuery({
    queryKey: ["plans", planId],
    queryFn: () => getPlan(planId ?? ""),
    enabled: Boolean(planId),
  });
  const accounts = useQuery({
    queryKey: ["plans", planId, "accounts"],
    queryFn: () => getAccounts(planId ?? ""),
    enabled: Boolean(planId),
  });
  const [name, setName] = useState("");
  const [accountType, setAccountType] = useState<(typeof ACCOUNT_TYPES)[number]>("Bank");
  const [currency, setCurrency] = useState("BOB");
  const createMutation = useMutation({
    mutationFn: () => createAccount(planId ?? "", newClientId(), {
      name,
      account_type: accountType,
      currency_code: currency,
    }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["plans", planId, "accounts"] });
      setName("");
    },
  });

  if (!planId) return <Navigate to="/plans" replace />;

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <Link to="/plans">← Plans</Link>
          <p className="eyebrow">Selected Plan</p>
          <h1>{plan.data?.name ?? "Accounts"}</h1>
          <p>Reporting currency: {plan.data?.reporting_currency_code ?? "…"}</p>
        </div>
      </header>

      <section className="panel" aria-labelledby="create-account-heading">
        <h2 id="create-account-heading">Create an Account</h2>
        <form
          className="form-grid"
          onSubmit={(event) => {
            event.preventDefault();
            createMutation.mutate();
          }}
        >
          <label>
            Name
            <input
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Main wallet"
            />
          </label>
          <label>
            Type
            <select
              value={accountType}
              onChange={(event) => setAccountType(event.target.value as typeof accountType)}
            >
              {ACCOUNT_TYPES.map((type) => <option key={type}>{type}</option>)}
            </select>
          </label>
          <label>
            Currency
            <select
              value={currency}
              onChange={(event) => setCurrency(event.target.value)}
              disabled={currencies.isPending}
            >
              {(currencies.data ?? []).map((item) => (
                <option key={item.code} value={item.code}>{item.code}</option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={createMutation.isPending || !name.trim()}>
            {createMutation.isPending ? "Creating…" : "Create Account"}
          </button>
        </form>
        {createMutation.isError && <ErrorMessage message={createMutation.error.message} />}
      </section>

      <section className="panel" aria-labelledby="accounts-heading">
        <h2 id="accounts-heading">Accounts</h2>
        {accounts.isPending && <p>Loading Accounts…</p>}
        {accounts.isError && <ErrorMessage message="Accounts could not be loaded." />}
        {accounts.data?.length === 0 && <p>No Accounts yet.</p>}
        <div className="card-list">
          {accounts.data?.map((account) => (
            <AccountCard key={account.id} account={account} planId={planId} />
          ))}
        </div>
      </section>
      <ExchangeRatesPanel planId={planId} />
      <WatchersPanel planId={planId} />
      <MatchingPanel planId={planId} />
      <AISettingsPanel planId={planId} />
      <p>
        <Link className="button" to={`/plans/${planId}/ledger`}>Open Ledger</Link>{" "}
        <Link className="button" to={`/plans/${planId}/analytics`}>Open Analytics</Link>
      </p>
    </main>
  );
}

function ExchangeRatesPanel({ planId }: { planId: string }) {
  const queryClient = useQueryClient();

  const providersQuery = useQuery({
    queryKey: ["plans", planId, "fx", "providers"],
    queryFn: () => getFXProviders(planId),
  });

  const latestQuoteQuery = useQuery({
    queryKey: ["plans", planId, "fx", "latest"],
    queryFn: () => getLatestQuote(planId),
  });

  const quotesQuery = useQuery({
    queryKey: ["plans", planId, "fx", "quotes"],
    queryFn: () => getQuotes(planId),
  });

  const [side, setSide] = useState<"BUY_USDT" | "SELL_USDT">("BUY_USDT");
  const [bobAmount, setBobAmount] = useState("");
  const [usdtAmount, setUsdtAmount] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("");
  const [feeAmount, setFeeAmount] = useState("");
  const [minLimit, setMinLimit] = useState("");
  const [maxLimit, setMaxLimit] = useState("");
  const [quoteMessage, setQuoteMessage] = useState<string | null>(null);

  const [convertDirection, setConvertDirection] = useState<"BOB_TO_USDT" | "USDT_TO_BOB">("BOB_TO_USDT");
  const [convertAmount, setConvertAmount] = useState("");
  const [customRate, setCustomRate] = useState("");
  const [convertResult, setConvertResult] = useState<ConvertResponse | null>(null);
  const [convertError, setConvertError] = useState<string | null>(null);

  const liveRate =
    bobAmount && usdtAmount && Number(usdtAmount) > 0
      ? (Number(bobAmount) / Number(usdtAmount)).toFixed(8)
      : null;

  const createQuoteMutation = useMutation({
    mutationFn: () =>
      createQuote(planId, {
        side,
        bob_amount: bobAmount,
        usdt_amount: usdtAmount,
        payment_method: paymentMethod.trim() || null,
        fee_amount: feeAmount.trim() || undefined,
        min_limit: minLimit.trim() || undefined,
        max_limit: maxLimit.trim() || undefined,
        source: "manual",
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "fx", "latest"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "fx", "quotes"] }),
      ]);
      setBobAmount("");
      setUsdtAmount("");
      setPaymentMethod("");
      setFeeAmount("");
      setMinLimit("");
      setMaxLimit("");
      setQuoteMessage("Quote recorded successfully.");
      setTimeout(() => setQuoteMessage(null), 4000);
    },
  });

  const convertMutation = useMutation({
    mutationFn: () => {
      const fromCurr = convertDirection === "BOB_TO_USDT" ? "BOB" : "USDT";
      const toCurr = convertDirection === "BOB_TO_USDT" ? "USDT" : "BOB";
      return convertCurrency(planId, {
        from_currency: fromCurr,
        to_currency: toCurr,
        amount: convertAmount,
        custom_rate: customRate.trim() || undefined,
      });
    },
    onSuccess: (data) => {
      setConvertResult(data);
      setConvertError(null);
    },
    onError: (err: any) => {
      setConvertResult(null);
      setConvertError(err.message || "Failed to convert currency");
    },
  });

  const latest = latestQuoteQuery.data;

  return (
    <section className="panel" aria-labelledby="fx-heading" data-testid="fx-panel">
      <h2 id="fx-heading">Exchange Rates & FX (BOB / USDT)</h2>

      <div className="fx-formula-banner" data-testid="fx-formula-banner">
        <strong>Explicit FX Formulas:</strong>
        <ul style={{ margin: "0.25rem 0 0.5rem 1.25rem" }}>
          <li><code>BUY_USDT</code>: rate = BOB paid / USDT received</li>
          <li><code>SELL_USDT</code>: rate = BOB received / USDT sold</li>
        </ul>
        <small>
          <em>Note: Official BCB rate (6.96) is reference-only and never assumed as a primary conversion rate. All conversions are explicit with complete rate provenance.</em>
        </small>
      </div>

      <h3>Latest Market Rates</h3>
      <div className="fx-quote-grid" data-testid="latest-rates-overview">
        <div className="card" data-testid="latest-buy-card">
          <p className="eyebrow">BUY USDT (Pay BOB → Get USDT)</p>
          {latest?.buy_quote ? (
            <div>
              <h3 style={{ margin: "0.25rem 0" }}>{latest.buy_quote.rate} BOB/USDT</h3>
              <p style={{ margin: "0.25rem 0", fontSize: "0.85rem", color: "#64748b" }}>
                Paid {latest.buy_quote.bob_amount} BOB for {latest.buy_quote.usdt_amount} USDT
              </p>
              <span className={latest.buy_quote.is_stale ? "freshness-stale" : "freshness-fresh"} data-testid="buy-freshness-badge">
                {latest.buy_quote.is_stale ? "Stale (>24h)" : "Fresh"}
              </span>
            </div>
          ) : (
            <p style={{ color: "#64748b" }}>No BUY_USDT quote recorded.</p>
          )}
        </div>

        <div className="card" data-testid="latest-sell-card">
          <p className="eyebrow">SELL USDT (Sell USDT → Get BOB)</p>
          {latest?.sell_quote ? (
            <div>
              <h3 style={{ margin: "0.25rem 0" }}>{latest.sell_quote.rate} BOB/USDT</h3>
              <p style={{ margin: "0.25rem 0", fontSize: "0.85rem", color: "#64748b" }}>
                Received {latest.sell_quote.bob_amount} BOB for {latest.sell_quote.usdt_amount} USDT
              </p>
              <span className={latest.sell_quote.is_stale ? "freshness-stale" : "freshness-fresh"} data-testid="sell-freshness-badge">
                {latest.sell_quote.is_stale ? "Stale (>24h)" : "Fresh"}
              </span>
            </div>
          ) : (
            <p style={{ color: "#64748b" }}>No SELL_USDT quote recorded.</p>
          )}
        </div>
      </div>

      <h3>FX Providers</h3>
      <div data-testid="fx-providers-list" style={{ marginBottom: "1.5rem" }}>
        {providersQuery.data?.map((prov) => (
          <div key={prov.id} className="card" style={{ marginBottom: "0.5rem", padding: "0.75rem" }} data-testid={`provider-status-${prov.id}`}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <strong>{prov.name}</strong>
              <span
                className={
                  prov.status === "available"
                    ? "freshness-fresh"
                    : prov.status === "reference_only"
                    ? "status-high"
                    : "status-new"
                }
              >
                {prov.status.toUpperCase()} {prov.is_primary ? "(Primary)" : ""}
              </span>
            </div>
            <p style={{ margin: "0.25rem 0 0 0", fontSize: "0.85rem", color: "#475569" }}>
              {prov.description}
            </p>
            {prov.notes && (
              <small style={{ color: "#64748b" }}>{prov.notes}</small>
            )}
          </div>
        ))}
      </div>

      <h3>Record Manual Quote</h3>
      <form
        className="form-grid"
        data-testid="create-fx-quote-form"
        onSubmit={(e) => {
          e.preventDefault();
          createQuoteMutation.mutate();
        }}
      >
        <label>
          Side
          <select
            value={side}
            onChange={(e) => setSide(e.target.value as "BUY_USDT" | "SELL_USDT")}
            data-testid="quote-side-select"
          >
            <option value="BUY_USDT">BUY_USDT (Paying BOB for USDT)</option>
            <option value="SELL_USDT">SELL_USDT (Selling USDT for BOB)</option>
          </select>
        </label>
        <label>
          BOB Amount
          <input
            type="number"
            step="0.01"
            required
            placeholder="e.g. 75.50"
            value={bobAmount}
            onChange={(e) => setBobAmount(e.target.value)}
            data-testid="quote-bob-amount"
          />
        </label>
        <label>
          USDT Amount
          <input
            type="number"
            step="0.000001"
            required
            placeholder="e.g. 10.00"
            value={usdtAmount}
            onChange={(e) => setUsdtAmount(e.target.value)}
            data-testid="quote-usdt-amount"
          />
        </label>
        <label>
          Payment Method
          <input
            placeholder="e.g. QR Interbancario, Cash"
            value={paymentMethod}
            onChange={(e) => setPaymentMethod(e.target.value)}
            data-testid="quote-payment-method"
          />
        </label>
        <label>
          Fee (Optional)
          <input
            type="number"
            step="0.01"
            placeholder="0.00"
            value={feeAmount}
            onChange={(e) => setFeeAmount(e.target.value)}
            data-testid="quote-fee-amount"
          />
        </label>
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "flex-end" }}>
          {liveRate && (
            <p style={{ margin: "0 0 0.5rem 0", fontSize: "0.85rem", fontWeight: "bold", color: "#166534" }} data-testid="quote-live-rate">
              Computed Rate: {liveRate} BOB/USDT
            </p>
          )}
          <button
            type="submit"
            disabled={createQuoteMutation.isPending || !bobAmount || !usdtAmount}
            data-testid="save-quote-button"
          >
            {createQuoteMutation.isPending ? "Saving…" : "Save Manual Quote"}
          </button>
        </div>
      </form>
      {quoteMessage && <p style={{ color: "#166534", marginTop: "0.5rem" }} data-testid="quote-success-message">{quoteMessage}</p>}
      {createQuoteMutation.isError && (
        <ErrorMessage message={createQuoteMutation.error.message} />
      )}

      <h3 style={{ marginTop: "2rem" }}>Currency Conversion Calculator</h3>
      <form
        className="form-grid"
        data-testid="currency-converter-widget"
        onSubmit={(e) => {
          e.preventDefault();
          convertMutation.mutate();
        }}
      >
        <label>
          Direction
          <select
            value={convertDirection}
            onChange={(e) => setConvertDirection(e.target.value as any)}
            data-testid="convert-direction-select"
          >
            <option value="BOB_TO_USDT">BOB → USDT (Buy USDT)</option>
            <option value="USDT_TO_BOB">USDT → BOB (Sell USDT)</option>
          </select>
        </label>
        <label>
          Amount to Convert
          <input
            type="number"
            step="0.000001"
            required
            placeholder={convertDirection === "BOB_TO_USDT" ? "BOB amount" : "USDT amount"}
            value={convertAmount}
            onChange={(e) => setConvertAmount(e.target.value)}
            data-testid="convert-amount-input"
          />
        </label>
        <label>
          Custom Rate (Optional Override)
          <input
            type="number"
            step="0.00000001"
            placeholder="e.g. 7.55"
            value={customRate}
            onChange={(e) => setCustomRate(e.target.value)}
            data-testid="convert-custom-rate-input"
          />
        </label>
        <div style={{ display: "flex", alignItems: "flex-end" }}>
          <button
            type="submit"
            disabled={convertMutation.isPending || !convertAmount}
            data-testid="convert-submit-button"
          >
            {convertMutation.isPending ? "Converting…" : "Calculate Conversion"}
          </button>
        </div>
      </form>

      {convertError && <ErrorMessage message={convertError} />}

      {convertResult && (
        <div className="fx-calc-result" data-testid="conversion-result">
          <h4 style={{ margin: "0 0 0.5rem 0" }}>Conversion Result</h4>
          <p style={{ fontSize: "1.2rem", fontWeight: "bold", margin: "0.25rem 0", color: "#1d4ed8" }} data-testid="conversion-result-value">
            {convertResult.from_amount} {convertResult.from_currency} = {convertResult.to_amount} {convertResult.to_currency}
          </p>
          <div style={{ fontSize: "0.85rem", color: "#475569", marginTop: "0.5rem" }}>
            <div><strong>Rate Used:</strong> {convertResult.rate_used} ({convertResult.rate_source})</div>
            <div><strong>Formula:</strong> {convertResult.formula}</div>
            <div>
              <strong>Freshness:</strong>{" "}
              <span className={convertResult.is_stale ? "freshness-stale" : "freshness-fresh"} data-testid="conversion-result-freshness">
                {convertResult.is_stale ? "Stale Quote Used" : "Fresh Rate"}
              </span>
            </div>
          </div>
        </div>
      )}

      <h3 style={{ marginTop: "2rem" }}>Quotes History</h3>
      {quotesQuery.isPending && <p>Loading quotes…</p>}
      {quotesQuery.data?.length === 0 && <p>No quotes recorded yet.</p>}
      {quotesQuery.data && quotesQuery.data.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table className="table" data-testid="quotes-history-table" style={{ width: "100%", textAlign: "left" }}>
            <thead>
              <tr>
                <th>Date/Time</th>
                <th>Side</th>
                <th>BOB Amount</th>
                <th>USDT Amount</th>
                <th>Rate (BOB/USDT)</th>
                <th>Method</th>
                <th>Source</th>
                <th>Freshness</th>
              </tr>
            </thead>
            <tbody>
              {quotesQuery.data.map((q) => (
                <tr key={q.id} data-testid={`quote-row-${q.id}`}>
                  <td>{new Date(q.observed_at).toLocaleString()}</td>
                  <td>
                    <span className={q.side === "BUY_USDT" ? "status-high" : "status-possible"}>
                      {q.side}
                    </span>
                  </td>
                  <td>{q.bob_amount} BOB</td>
                  <td>{q.usdt_amount} USDT</td>
                  <td><strong>{q.rate}</strong></td>
                  <td>{q.payment_method || "—"}</td>
                  <td>{q.source}</td>
                  <td>
                    <span className={q.is_stale ? "freshness-stale" : "freshness-fresh"}>
                      {q.freshness}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function AISettingsPanel({ planId }: { planId: string }) {
  const queryClient = useQueryClient();
  const config = useQuery({
    queryKey: ["plans", planId, "ai", "config"],
    queryFn: () => getAIConfig(planId),
  });
  const [provider, setProvider] = useState("openrouter");
  const [model, setModel] = useState("openai/gpt-4o-mini");
  const [apiKey, setApiKey] = useState("");
  const [isEnabled, setIsEnabled] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  useEffect(() => {
    if (config.data) {
      setProvider(config.data.provider);
      setModel(config.data.model);
      setIsEnabled(config.data.is_enabled);
      setBaseUrl(config.data.base_url || "");
      setApiKey("");
    }
  }, [config.data]);

  const models = useQuery({
    queryKey: ["plans", planId, "ai", "models", provider],
    queryFn: () => getAIModels(planId, provider),
  });

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload: AIConfigUpdate = {
        provider,
        model,
        is_enabled: isEnabled,
        base_url: baseUrl.trim() || undefined,
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
      };
      return updateAIConfig(planId, payload);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["plans", planId, "ai", "config"] });
      setApiKey("");
      setStatusMessage("AI configuration saved successfully.");
    },
  });

  const clearKeyMutation = useMutation({
    mutationFn: () => updateAIConfig(planId, { clear_api_key: true }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["plans", planId, "ai", "config"] });
      setStatusMessage("API key cleared.");
    },
  });

  return (
    <section className="panel" aria-labelledby="ai-settings-heading" data-testid="ai-settings-panel">
      <h2 id="ai-settings-heading">AI Assistant Settings</h2>
      <p className="field-help">
        AI assistance is strictly optional and bounded. It provides non-authoritative recommendations for categorization and merchant normalization.
      </p>
      {statusMessage && (
        <p className="field-help" role="status" style={{ color: "#15803d" }} data-testid="ai-status-message">
          {statusMessage}
        </p>
      )}
      <form
        className="form-grid"
        onSubmit={(e) => {
          e.preventDefault();
          saveMutation.mutate();
        }}
      >
        <label>
          <input
            type="checkbox"
            checked={isEnabled}
            onChange={(e) => setIsEnabled(e.target.checked)}
            data-testid="ai-enabled-checkbox"
          />
          Enable AI Assistant
        </label>
        <label>
          Provider
          <select
            value={provider}
            onChange={(e) => {
              const nextProvider = e.target.value;
              setProvider(nextProvider);
              if (nextProvider === "groq") setModel("llama-3.3-70b-versatile");
              else if (nextProvider === "openrouter") setModel("openai/gpt-4o-mini");
            }}
            data-testid="ai-provider-select"
          >
            <option value="openrouter">OpenRouter</option>
            <option value="groq">Groq</option>
            <option value="custom">Custom (OpenAI-compatible)</option>
          </select>
        </label>
        <label>
          Model
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            list="recommended-models"
            required
            data-testid="ai-model-input"
          />
          <datalist id="recommended-models">
            {models.data?.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name} {m.recommended ? "(Recommended)" : ""}
              </option>
            ))}
          </datalist>
        </label>
        <label>
          API Key
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={config.data?.has_api_key ? "•••••••• (Key configured)" : "Enter API Key"}
            data-testid="ai-api-key-input"
          />
        </label>
        {config.data?.has_api_key && (
          <button
            type="button"
            className="secondary"
            onClick={() => clearKeyMutation.mutate()}
            disabled={clearKeyMutation.isPending}
            data-testid="clear-ai-key-button"
          >
            Clear Stored Key
          </button>
        )}
        <label>
          Custom Base URL (optional)
          <input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://..."
            data-testid="ai-base-url-input"
          />
        </label>
        <button
          type="submit"
          disabled={saveMutation.isPending}
          data-testid="save-ai-config-button"
        >
          {saveMutation.isPending ? "Saving…" : "Save AI Settings"}
        </button>
      </form>
      {saveMutation.isError && <ErrorMessage message={saveMutation.error.message} />}
    </section>
  );
}

function WatchersPanel({ planId }: { planId: string }) {
  const queryClient = useQueryClient();
  const sources = useQuery({
    queryKey: ["plans", planId, "watchers", "sources"],
    queryFn: () => getWatcherSources(planId),
  });
  const messages = useQuery({
    queryKey: ["plans", planId, "watchers", "messages"],
    queryFn: () => getWatcherMessages(planId),
  });
  const candidates = useQuery({
    queryKey: ["plans", planId, "watchers", "candidates"],
    queryFn: () => getWatcherCandidates(planId),
  });
  const mappings = useQuery({
    queryKey: ["plans", planId, "watchers", "mappings"],
    queryFn: () => getWatcherAccountMappings(planId),
  });
  const rules = useQuery({
    queryKey: ["plans", planId, "rules"],
    queryFn: () => getRules(planId),
  });
  const automationSuggestions = useQuery({
    queryKey: ["plans", planId, "automation", "suggestions"],
    queryFn: () => getAutomationSuggestions(planId),
  });
  const accounts = useQuery({
    queryKey: ["plans", planId, "accounts"],
    queryFn: () => getAccounts(planId),
  });
  const categories = useQuery({
    queryKey: ["plans", planId, "categories"],
    queryFn: () => getCategories(planId),
  });

  const [showConnect, setShowConnect] = useState(false);
  const [authCode, setAuthCode] = useState("");
  const [redirectUri, setRedirectUri] = useState(
    typeof window !== "undefined"
      ? `${window.location.origin}/oauth/callback`
      : "http://localhost:5173/oauth/callback"
  );
  const [syncStatus, setSyncStatus] = useState<string | null>(null);

  // Resolving Candidate State
  const [resolvingCandidateId, setResolvingCandidateId] = useState<string | null>(null);
  const [resolveAccountId, setResolveAccountId] = useState("");
  const [resolveCategoryId, setResolveCategoryId] = useState("");
  const [resolveAmount, setResolveAmount] = useState("");
  const [resolveMemo, setResolveMemo] = useState("");

  // New Mapping State
  const [newMappingPattern, setNewMappingPattern] = useState("*");
  const [newMappingAccountId, setNewMappingAccountId] = useState("");
  const [newMappingCategoryId, setNewMappingCategoryId] = useState("");
  const [newMappingAutoResolve, setNewMappingAutoResolve] = useState(false);

  // New Rule State
  const [newRuleName, setNewRuleName] = useState("");
  const [newRulePriority, setNewRulePriority] = useState("100");
  const [newRulePredicateField, setNewRulePredicateField] = useState("raw_glosa");
  const [newRulePredicateValue, setNewRulePredicateValue] = useState("");
  const [newRuleActionField, setNewRuleActionField] = useState("qr_subtype");
  const [newRuleActionValue, setNewRuleActionValue] = useState("");

  const authUrlQuery = useQuery({
    queryKey: ["plans", planId, "watchers", "gmail", "auth-url", redirectUri],
    queryFn: () => getGmailAuthUrl(planId, redirectUri),
    enabled: showConnect,
  });

  const connectMutation = useMutation({
    mutationFn: () => connectGmail(planId, authCode, redirectUri),
    onSuccess: async () => {
      setAuthCode("");
      setShowConnect(false);
      await queryClient.invalidateQueries({
        queryKey: ["plans", planId, "watchers", "sources"],
      });
    },
  });

  const syncMutation = useMutation({
    mutationFn: (sourceId: string) => syncWatcherSource(planId, sourceId),
    onSuccess: async (data) => {
      setSyncStatus(
        `Synced: ${data.synced_count} messages checked, ${data.new_messages_count} new messages ingested.`
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "watchers", "sources"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "watchers", "messages"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "watchers", "candidates"] }),
      ]);
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: (sourceId: string) => disconnectWatcherSource(planId, sourceId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["plans", planId, "watchers", "sources"],
      });
    },
  });

  const processMutation = useMutation({
    mutationFn: () => processWatcherCandidates(planId),
    onSuccess: async (data) => {
      setSyncStatus(
        `Processed: ${data.processed_count} messages, ${data.candidates_created} candidates created (${data.candidates_quarantined} quarantined, ${data.candidates_resolved} auto-resolved).`
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "watchers", "candidates"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "watchers", "messages"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "transactions"] }),
      ]);
    },
  });

  const replayRulesMutation = useMutation({
    mutationFn: () => replayRules(planId),
    onSuccess: async (data) => {
      setSyncStatus(
        `Rules replayed: ${data.replayed_count} candidate(s) evaluated (${data.modified_count} updated, ${data.quarantined_count} quarantined, ${data.resolved_count} resolved).`
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "watchers", "candidates"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "transactions"] }),
      ]);
    },
  });

  const resolveMutation = useMutation({
    mutationFn: ({ candidateId, payload }: { candidateId: string; payload: any }) =>
      resolveWatcherCandidate(planId, candidateId, payload),
    onSuccess: async () => {
      setResolvingCandidateId(null);
      setResolveAccountId("");
      setResolveCategoryId("");
      setResolveAmount("");
      setResolveMemo("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "watchers", "candidates"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "accounts"] }),
      ]);
    },
  });

  const ignoreMutation = useMutation({
    mutationFn: (candidateId: string) => ignoreWatcherCandidate(planId, candidateId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["plans", planId, "watchers", "candidates"],
      });
    },
  });

  const aiSuggestions = useQuery({
    queryKey: ["plans", planId, "ai", "suggestions"],
    queryFn: () => getAISuggestions(planId),
  });

  const suggestCandidateMutation = useMutation({
    mutationFn: (candidateId: string) => generateCandidateSuggestion(planId, candidateId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["plans", planId, "ai", "suggestions"] });
    },
  });

  const acceptAISuggestionMutation = useMutation({
    mutationFn: (suggestionId: string) => acceptAISuggestion(planId, suggestionId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "ai", "suggestions"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "watchers", "candidates"] }),
      ]);
    },
  });

  const rejectAISuggestionMutation = useMutation({
    mutationFn: ({ suggestionId, reason }: { suggestionId: string; reason?: string }) =>
      rejectAISuggestion(planId, suggestionId, reason),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["plans", planId, "ai", "suggestions"] });
    },
  });

  const createMappingMutation = useMutation({
    mutationFn: () =>
      createWatcherAccountMapping(planId, {
        source_type: "binance_card",
        pattern: newMappingPattern,
        account_id: newMappingAccountId,
        default_category_id: newMappingCategoryId || null,
        auto_resolve: newMappingAutoResolve,
      }),
    onSuccess: async () => {
      setNewMappingPattern("*");
      setNewMappingAccountId("");
      setNewMappingCategoryId("");
      setNewMappingAutoResolve(false);
      await queryClient.invalidateQueries({
        queryKey: ["plans", planId, "watchers", "mappings"],
      });
    },
  });

  const deleteMappingMutation = useMutation({
    mutationFn: (mappingId: string) => deleteWatcherAccountMapping(planId, mappingId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["plans", planId, "watchers", "mappings"],
      });
    },
  });

  const createRuleMutation = useMutation({
    mutationFn: () => {
      const priorityNum = parseInt(newRulePriority, 10) || 100;
      const predicate = { [newRulePredicateField]: newRulePredicateValue };
      const action = { [newRuleActionField]: newRuleActionValue };
      return createRule(planId, {
        name: newRuleName,
        stage: "watcher_candidate",
        priority: priorityNum,
        enabled: true,
        predicate,
        action,
      });
    },
    onSuccess: async () => {
      setNewRuleName("");
      setNewRulePriority("100");
      setNewRulePredicateValue("");
      setNewRuleActionValue("");
      await queryClient.invalidateQueries({
        queryKey: ["plans", planId, "rules"],
      });
    },
  });

  const updateRuleMutation = useMutation({
    mutationFn: ({ ruleId, payload }: { ruleId: string; payload: any }) =>
      updateRule(planId, ruleId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["plans", planId, "rules"],
      });
    },
  });

  const deleteRuleMutation = useMutation({
    mutationFn: (ruleId: string) => deleteRule(planId, ruleId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["plans", planId, "rules"],
      });
    },
  });

  const discoverSuggestionsMutation = useMutation({
    mutationFn: () => discoverAutomationSuggestions(planId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["plans", planId, "automation", "suggestions"],
      });
    },
  });

  const acceptSuggestionMutation = useMutation({
    mutationFn: (suggestionId: string) =>
      acceptAutomationSuggestion(planId, suggestionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["plans", planId, "automation", "suggestions"],
      });
      await queryClient.invalidateQueries({
        queryKey: ["plans", planId, "rules"],
      });
    },
  });

  const dismissSuggestionMutation = useMutation({
    mutationFn: (suggestionId: string) =>
      dismissAutomationSuggestion(planId, suggestionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["plans", planId, "automation", "suggestions"],
      });
    },
  });

  const activeAccounts = accounts.data?.filter((a) => a.status === "active") || [];
  const activeCategories = categories.data?.filter((c) => c.status === "active") || [];

  return (
    <section className="panel" aria-labelledby="watchers-heading" data-testid="watchers-panel">
      <h2 id="watchers-heading">Gmail Watchers & Integrations</h2>
      <p>Synchronize email transaction notices safely and idempotently.</p>

      <div className="card-actions">
        <button type="button" onClick={() => setShowConnect(!showConnect)}>
          {showConnect ? "Hide Connect" : "Connect Gmail"}
        </button>
        <button
          type="button"
          disabled={processMutation.isPending}
          onClick={() => processMutation.mutate()}
        >
          {processMutation.isPending ? "Processing…" : "Process Candidates"}
        </button>
        <button
          type="button"
          data-testid="replay-rules-button"
          disabled={replayRulesMutation.isPending}
          onClick={() => replayRulesMutation.mutate()}
        >
          {replayRulesMutation.isPending ? "Replaying…" : "Replay Rules"}
        </button>
      </div>

      {showConnect && (
        <div className="connect-watcher-form" data-testid="connect-gmail-panel">
          <h3>Connect Gmail Watcher</h3>
          {authUrlQuery.data?.auth_url && (
            <p>
              1. Authorize via Google:{" "}
              <a
                href={authUrlQuery.data.auth_url}
                target="_blank"
                rel="noreferrer"
                className="button"
              >
                Open Google Authorization
              </a>
            </p>
          )}
          {authUrlQuery.isError && (
            <ErrorMessage message="Could not generate OAuth URL (is Gmail configured?)." />
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              connectMutation.mutate();
            }}
            className="form-grid"
          >
            <label>
              Redirect URI
              <input
                value={redirectUri}
                onChange={(e) => setRedirectUri(e.target.value)}
                required
              />
            </label>
            <label>
              Authorization Code
              <input
                value={authCode}
                onChange={(e) => setAuthCode(e.target.value)}
                placeholder="4/0AWtgzh..."
                required
              />
            </label>
            <button
              type="submit"
              disabled={connectMutation.isPending || !authCode.trim()}
            >
              {connectMutation.isPending ? "Connecting…" : "Complete Connection"}
            </button>
          </form>
          {connectMutation.isError && (
            <ErrorMessage message={connectMutation.error.message} />
          )}
        </div>
      )}

      {syncStatus && <p className="field-help">{syncStatus}</p>}
      {syncMutation.isError && <ErrorMessage message={syncMutation.error.message} />}
      {disconnectMutation.isError && (
        <ErrorMessage message={disconnectMutation.error.message} />
      )}
      {processMutation.isError && <ErrorMessage message={processMutation.error.message} />}
      {replayRulesMutation.isError && (
        <ErrorMessage message={replayRulesMutation.error.message} />
      )}

      <div className="card-list">
        {sources.isPending && <p>Loading watchers…</p>}
        {sources.isError && <ErrorMessage message="Watchers could not be loaded." />}
        {sources.data?.length === 0 && <p>No Gmail sources connected.</p>}
        {sources.data?.map((source) => (
          <article className="card" key={source.id} data-testid={`watcher-source-${source.id}`}>
            <div className="account-heading">
              <div>
                <h3>{source.email_address}</h3>
                <p>Provider: {source.source_type}</p>
                {source.history_id && <p>History cursor: {source.history_id}</p>}
                {source.last_sync_at && <p>Last sync: {source.last_sync_at}</p>}
              </div>
              <span className={`status status-${source.status}`}>{source.status}</span>
            </div>
            {source.status === "active" && (
              <div className="card-actions">
                <button
                  type="button"
                  disabled={syncMutation.isPending}
                  onClick={() => syncMutation.mutate(source.id)}
                >
                  {syncMutation.isPending ? "Syncing…" : "Sync Now"}
                </button>
                <button
                  type="button"
                  disabled={disconnectMutation.isPending}
                  onClick={() => disconnectMutation.mutate(source.id)}
                >
                  Disconnect
                </button>
              </div>
            )}
          </article>
        ))}
      </div>

      {/* Watcher Candidates Section */}
      <div className="candidates-section" data-testid="watcher-candidates-section">
        <h3>Candidates & Bank Notices ({candidates.data?.length ?? 0})</h3>
        {candidates.isPending && <p>Loading candidates…</p>}
        {candidates.isError && <ErrorMessage message="Candidates could not be loaded." />}
        {candidates.data?.length === 0 && <p>No transaction candidates found.</p>}

        {resolveMutation.isError && (
          <ErrorMessage message={resolveMutation.error.message} />
        )}

        <div className="card-list">
          {candidates.data?.map((c) => {
            const isResolving = resolvingCandidateId === c.id;
            const selectedAccount = activeAccounts.find((a) => a.id === resolveAccountId);

            return (
              <article className="card" key={c.id} data-testid={`watcher-candidate-${c.id}`}>
                <div className="account-heading">
                  <div>
                    <span className="status" style={{ marginRight: "0.5rem" }}>
                      {c.candidate_type}
                    </span>
                    <strong>{c.merchant ? `Merchant: ${c.merchant}` : c.subject}</strong>
                    <p>
                      Reported: <strong>{c.reported_amount} {c.reported_currency}</strong> · Event:{" "}
                      {c.event_at ? c.event_at : <em>Pending Statement Enrichment</em>}
                    </p>
                    {c.notification_at && <p>Notification: {c.notification_at}</p>}
                    {c.direction && <p>Direction: <strong>{c.direction}</strong></p>}
                    {c.account_suffix && <p>Account Suffix: <strong>{c.account_suffix}</strong></p>}
                    {(c.glosa || c.raw_glosa) && (
                      <p>
                        Glosa: <code>{c.glosa || c.raw_glosa}</code>
                      </p>
                    )}
                    {c.qr_subtype && (
                      <p>
                        QR Subtype: <span className="status">{c.qr_subtype}</span>
                      </p>
                    )}
                    {c.provider_uuid && <p className="field-help">UUID: {c.provider_uuid}</p>}
                  </div>
                  <span className={`status status-${c.status}`}>{c.status}</span>
                </div>

                {c.quarantine_reason && (
                  <p
                    className="field-help"
                    role="alert"
                    data-testid={`quarantine-reason-${c.id}`}
                    style={{
                      color: "#b91c1c",
                      fontWeight: c.quarantine_reason === "rule_conflict" ? "bold" : "normal",
                    }}
                  >
                    {c.quarantine_reason === "rule_conflict"
                      ? "⚠️ Quarantine: Rule Conflict Detected"
                      : c.quarantine_reason}
                  </p>
                )}

                {c.rule_evidence && c.rule_evidence.length > 0 && (
                  <details style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
                    <summary>Rule Evidence ({c.rule_evidence.length})</summary>
                    <ul>
                      {c.rule_evidence.map((ev, idx) => (
                        <li key={idx}>
                          <strong>{ev.rule_name}</strong>: {ev.result}
                          {ev.conflicting_field && (
                            <span>
                              {" "}(Conflict on <code>{ev.conflicting_field}</code>: existing=
                              {String(ev.existing_value)}, attempted={String(ev.attempted_value)})
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}

                {/* AI Suggestions Badge */}
                {(() => {
                  const candidateSuggestions = aiSuggestions.data?.filter(
                    (s) => s.candidate_id === c.id && (s.status === "suggested" || s.status === "quarantined")
                  );
                  if (!candidateSuggestions || candidateSuggestions.length === 0) return null;
                  return (
                    <div
                      className="ai-suggestion-badge"
                      data-testid={`ai-suggestion-candidate-${c.id}`}
                      style={{
                        marginTop: "0.5rem",
                        padding: "0.5rem",
                        background: "#f0fdf4",
                        border: "1px solid #bbf7d0",
                        borderRadius: "4px",
                      }}
                    >
                      {candidateSuggestions.map((s) => {
                        const catName = categories.data?.find((cat) => cat.id === s.suggested_category_id)?.name;
                        return (
                          <div key={s.id} data-testid={`ai-suggestion-item-${s.id}`}>
                            <span
                              className="status"
                              style={{
                                background: s.status === "quarantined" ? "#fef2f2" : "#dcfce7",
                                color: s.status === "quarantined" ? "#991b1b" : "#166534",
                              }}
                            >
                              {s.status === "quarantined" ? "AI Quarantined" : "AI Suggestion"}
                            </span>
                            {s.status === "suggested" && (
                              <p style={{ margin: "0.25rem 0", fontSize: "0.9rem" }}>
                                {catName && <span>Category: <strong>{catName}</strong> · </span>}
                                {s.suggested_merchant && <span>Merchant: <strong>{s.suggested_merchant}</strong> · </span>}
                                {s.confidence && <span>Confidence: {(Number(s.confidence) * 100).toFixed(0)}%</span>}
                              </p>
                            )}
                            {s.reasoning && (
                              <p className="field-help" style={{ margin: "0.25rem 0" }}>
                                {s.reasoning}
                              </p>
                            )}
                            {s.status === "suggested" && (
                              <div className="card-actions" style={{ marginTop: "0.25rem" }}>
                                <button
                                  type="button"
                                  data-testid={`accept-ai-suggestion-${s.id}`}
                                  disabled={acceptAISuggestionMutation.isPending}
                                  onClick={() => {
                                    if (s.suggested_category_id) setResolveCategoryId(s.suggested_category_id);
                                    acceptAISuggestionMutation.mutate(s.id);
                                  }}
                                >
                                  Apply Suggestion
                                </button>
                                <button
                                  type="button"
                                  data-testid={`reject-ai-suggestion-${s.id}`}
                                  disabled={rejectAISuggestionMutation.isPending}
                                  onClick={() => rejectAISuggestionMutation.mutate({ suggestionId: s.id })}
                                >
                                  Dismiss
                                </button>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  );
                })()}

                {c.status === "resolved" && (
                  <p className="field-help" style={{ color: "#15803d" }}>
                    Resolved to settlement: {c.settlement_amount} {c.settlement_currency}
                  </p>
                )}

                {(c.status === "pending" || c.status === "quarantined") && !isResolving && (
                  <div className="card-actions">
                    <button
                      type="button"
                      onClick={() => {
                        setResolvingCandidateId(c.id);
                        setResolveAmount(c.reported_amount);
                        setResolveAccountId(activeAccounts[0]?.id || "");
                      }}
                    >
                      Resolve…
                    </button>
                    <button
                      type="button"
                      data-testid={`ai-suggest-candidate-${c.id}`}
                      disabled={suggestCandidateMutation.isPending}
                      onClick={() => suggestCandidateMutation.mutate(c.id)}
                    >
                      {suggestCandidateMutation.isPending ? "Analyzing…" : "Suggest with AI"}
                    </button>
                    <button
                      type="button"
                      disabled={ignoreMutation.isPending}
                      onClick={() => ignoreMutation.mutate(c.id)}
                    >
                      Ignore
                    </button>
                  </div>
                )}

                {isResolving && (
                  <form
                    className="form-grid"
                    data-testid={`resolve-candidate-form-${c.id}`}
                    onSubmit={(e) => {
                      e.preventDefault();
                      resolveMutation.mutate({
                        candidateId: c.id,
                        payload: {
                          account_id: resolveAccountId,
                          category_id: resolveCategoryId || null,
                          settlement_amount: resolveAmount,
                          settlement_currency: selectedAccount?.currency_code,
                          memo: resolveMemo || undefined,
                        },
                      });
                    }}
                  >
                    <label>
                      Target Account
                      <select
                        value={resolveAccountId}
                        onChange={(e) => setResolveAccountId(e.target.value)}
                        required
                      >
                        <option value="" disabled>Select Account</option>
                        {activeAccounts.map((acc) => (
                          <option key={acc.id} value={acc.id}>
                            {acc.name} ({acc.currency_code})
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Category (Optional)
                      <select
                        value={resolveCategoryId}
                        onChange={(e) => setResolveCategoryId(e.target.value)}
                      >
                        <option value="">(Default: Pendientes)</option>
                        {activeCategories.map((cat) => (
                          <option key={cat.id} value={cat.id}>
                            {cat.name}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Settlement Amount ({selectedAccount?.currency_code || c.reported_currency})
                      <input
                        type="number"
                        step="any"
                        value={resolveAmount}
                        onChange={(e) => setResolveAmount(e.target.value)}
                        required
                      />
                    </label>

                    <label>
                      Memo
                      <input
                        value={resolveMemo}
                        onChange={(e) => setResolveMemo(e.target.value)}
                        placeholder={`${c.candidate_type} ${c.reported_amount} ${c.reported_currency}`}
                      />
                    </label>

                    <div className="card-actions">
                      <button type="submit" disabled={resolveMutation.isPending || !resolveAccountId}>
                        {resolveMutation.isPending ? "Resolving…" : "Confirm Resolution"}
                      </button>
                      <button
                        type="button"
                        onClick={() => setResolvingCandidateId(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                )}
              </article>
            );
          })}
        </div>
      </div>

      {/* Rules Section */}
      <div className="rules-section" data-testid="watcher-rules-section">
        <h3>Deterministic Rules & Classification ({rules.data?.length ?? 0})</h3>
        <p className="field-help">
          Rules classify bank notices deterministically by priority and quarantine conflicting outcomes.
        </p>

        {createRuleMutation.isError && (
          <ErrorMessage message={createRuleMutation.error.message} />
        )}
        {updateRuleMutation.isError && (
          <ErrorMessage message={updateRuleMutation.error.message} />
        )}
        {deleteRuleMutation.isError && (
          <ErrorMessage message={deleteRuleMutation.error.message} />
        )}

        <form
          className="form-grid"
          data-testid="create-rule-form"
          onSubmit={(e) => {
            e.preventDefault();
            createRuleMutation.mutate();
          }}
        >
          <label>
            Rule Name
            <input
              value={newRuleName}
              onChange={(e) => setNewRuleName(e.target.value)}
              placeholder="e.g. Classify QR Product Payments"
              required
            />
          </label>
          <label>
            Priority (Lower runs first)
            <input
              type="number"
              value={newRulePriority}
              onChange={(e) => setNewRulePriority(e.target.value)}
              required
            />
          </label>
          <label>
            Predicate Match Field
            <select
              value={newRulePredicateField}
              onChange={(e) => setNewRulePredicateField(e.target.value)}
            >
              <option value="raw_glosa">Raw Glosa (Exact)</option>
              <option value="merchant">Merchant</option>
              <option value="account_suffix">Account Suffix</option>
              <option value="candidate_type">Candidate Type</option>
              <option value="direction">Direction</option>
            </select>
          </label>
          <label>
            Predicate Match Value
            <input
              value={newRulePredicateValue}
              onChange={(e) => setNewRulePredicateValue(e.target.value)}
              placeholder="e.g. BM BM QR PAGO DE PRODUCTOS"
              required
            />
          </label>
          <label>
            Action Target Field
            <select
              value={newRuleActionField}
              onChange={(e) => setNewRuleActionField(e.target.value)}
            >
              <option value="qr_subtype">Set QR Subtype</option>
              <option value="merchant">Set Merchant</option>
            </select>
          </label>
          <label>
            Action Value
            <input
              value={newRuleActionValue}
              onChange={(e) => setNewRuleActionValue(e.target.value)}
              placeholder="e.g. product_payment"
              required
            />
          </label>
          <button
            type="submit"
            disabled={createRuleMutation.isPending || !newRuleName.trim() || !newRulePredicateValue.trim()}
          >
            {createRuleMutation.isPending ? "Creating Rule…" : "Create Rule"}
          </button>
        </form>

        <div className="card-list">
          {rules.isPending && <p>Loading rules…</p>}
          {rules.isError && <ErrorMessage message="Rules could not be loaded." />}
          {rules.data?.length === 0 && <p>No rules configured.</p>}
          {rules.data?.map((rule) => (
            <article className="card" key={rule.id} data-testid={`rule-card-${rule.id}`}>
              <div className="account-heading">
                <div>
                  <strong>{rule.name}</strong> (Priority: {rule.priority}, Stage: {rule.stage})
                  <p>
                    Predicate: <code>{JSON.stringify(rule.predicate)}</code>
                  </p>
                  <p>
                    Action: <code>{JSON.stringify(rule.action)}</code>
                  </p>
                </div>
                <span className={`status status-${rule.enabled ? "active" : "inactive"}`}>
                  {rule.enabled ? "Enabled" : "Disabled"}
                </span>
              </div>
              <div className="card-actions">
                <button
                  type="button"
                  disabled={updateRuleMutation.isPending}
                  onClick={() =>
                    updateRuleMutation.mutate({
                      ruleId: rule.id,
                      payload: { enabled: !rule.enabled },
                    })
                  }
                >
                  {rule.enabled ? "Disable" : "Enable"}
                </button>
                <button
                  type="button"
                  disabled={deleteRuleMutation.isPending}
                  onClick={() => deleteRuleMutation.mutate(rule.id)}
                >
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      </div>

      {/* Automation Suggestions Section */}
      <div className="automation-suggestions-section" data-testid="automation-suggestions-section">
        <div className="account-heading">
          <div>
            <h3>Automation Suggestions ({automationSuggestions.data?.filter((s) => s.status === "suggested").length ?? 0})</h3>
            <p className="field-help">
              Review pattern-detected rule proposals before promoting to deterministic rules.
            </p>
          </div>
          <button
            type="button"
            data-testid="discover-suggestions-button"
            disabled={discoverSuggestionsMutation.isPending}
            onClick={() => discoverSuggestionsMutation.mutate()}
          >
            {discoverSuggestionsMutation.isPending ? "Discovering…" : "Discover Suggestions"}
          </button>
        </div>

        {discoverSuggestionsMutation.isError && (
          <ErrorMessage message={discoverSuggestionsMutation.error.message} />
        )}
        {acceptSuggestionMutation.isError && (
          <ErrorMessage message={acceptSuggestionMutation.error.message} />
        )}
        {dismissSuggestionMutation.isError && (
          <ErrorMessage message={dismissSuggestionMutation.error.message} />
        )}

        <div className="card-list" data-testid="automation-suggestions-list">
          {automationSuggestions.isPending && <p>Loading suggestions…</p>}
          {automationSuggestions.isError && (
            <ErrorMessage message="Automation suggestions could not be loaded." />
          )}
          {automationSuggestions.data?.filter((s) => s.status === "suggested").length === 0 && (
            <p>No new rule suggestions available.</p>
          )}
          {automationSuggestions.data
            ?.filter((s) => s.status === "suggested")
            .map((suggestion) => (
              <article
                className="card"
                key={suggestion.id}
                data-testid={`automation-suggestion-card-${suggestion.id}`}
              >
                <div className="account-heading">
                  <div>
                    <strong>{suggestion.title}</strong>
                    {suggestion.confidence && (
                      <span> (Confidence: {Math.round(Number(suggestion.confidence) * 100)}%)</span>
                    )}
                    {suggestion.description && <p>{suggestion.description}</p>}
                    <p>
                      Predicate: <code>{JSON.stringify(suggestion.predicate)}</code>
                    </p>
                    <p>
                      Action: <code>{JSON.stringify(suggestion.action)}</code>
                    </p>
                    <p className="field-help">
                      Evidence: <code>{JSON.stringify(suggestion.evidence)}</code>
                    </p>
                  </div>
                  <span className="status status-suggested">Suggested</span>
                </div>
                <div className="card-actions">
                  <button
                    type="button"
                    data-testid={`accept-suggestion-button-${suggestion.id}`}
                    disabled={acceptSuggestionMutation.isPending}
                    onClick={() => acceptSuggestionMutation.mutate(suggestion.id)}
                  >
                    {acceptSuggestionMutation.isPending ? "Accepting…" : "Accept"}
                  </button>
                  <button
                    type="button"
                    data-testid={`dismiss-suggestion-button-${suggestion.id}`}
                    disabled={dismissSuggestionMutation.isPending}
                    onClick={() => dismissSuggestionMutation.mutate(suggestion.id)}
                  >
                    {dismissSuggestionMutation.isPending ? "Dismissing…" : "Dismiss"}
                  </button>
                </div>
              </article>
            ))}
        </div>
      </div>

      {/* Account Mappings Section */}
      <div className="mappings-section" data-testid="watcher-mappings-section">
        <h3>Authoritative Account Mappings ({mappings.data?.length ?? 0})</h3>
        <p className="field-help">
          Configure authoritative account mappings to resolve or auto-post notices.
        </p>

        {createMappingMutation.isError && (
          <ErrorMessage message={createMappingMutation.error.message} />
        )}

        <form
          className="form-grid"
          data-testid="create-mapping-form"
          onSubmit={(e) => {
            e.preventDefault();
            createMappingMutation.mutate();
          }}
        >
          <label>
            Source
            <input value="binance_card" disabled />
          </label>
          <label>
            Pattern (Merchant or *)
            <input
              value={newMappingPattern}
              onChange={(e) => setNewMappingPattern(e.target.value)}
              placeholder="*"
              required
            />
          </label>
          <label>
            Account
            <select
              value={newMappingAccountId}
              onChange={(e) => setNewMappingAccountId(e.target.value)}
              required
            >
              <option value="" disabled>Select Account</option>
              {activeAccounts.map((acc) => (
                <option key={acc.id} value={acc.id}>
                  {acc.name} ({acc.currency_code})
                </option>
              ))}
            </select>
          </label>
          <label>
            Category (Optional)
            <select
              value={newMappingCategoryId}
              onChange={(e) => setNewMappingCategoryId(e.target.value)}
            >
              <option value="">(Default: Pendientes)</option>
              {activeCategories.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.name}
                </option>
              ))}
            </select>
          </label>
          <label style={{ display: "flex", flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
            <input
              type="checkbox"
              checked={newMappingAutoResolve}
              onChange={(e) => setNewMappingAutoResolve(e.target.checked)}
            />
            Auto-resolve without review
          </label>
          <button
            type="submit"
            disabled={createMappingMutation.isPending || !newMappingAccountId}
          >
            {createMappingMutation.isPending ? "Saving…" : "Save Mapping"}
          </button>
        </form>

        <div className="card-list">
          {mappings.data?.map((m) => {
            const mappedAccount = activeAccounts.find((a) => a.id === m.account_id);
            return (
              <article className="card" key={m.id} data-testid={`watcher-mapping-${m.id}`}>
                <div className="account-heading">
                  <div>
                    <strong>{m.source_type}: {m.pattern}</strong>
                    <p>Mapped to: {mappedAccount ? `${mappedAccount.name} (${mappedAccount.currency_code})` : m.account_id}</p>
                    {m.auto_resolve && <p className="field-help">Auto-resolve enabled</p>}
                  </div>
                  <div className="card-actions">
                    <button
                      type="button"
                      disabled={deleteMappingMutation.isPending}
                      onClick={() => deleteMappingMutation.mutate(m.id)}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </div>

      <div className="raw-messages-section">
        <h3>Ingested Raw Messages ({messages.data?.length ?? 0})</h3>
        {messages.isPending && <p>Loading messages…</p>}
        {messages.isError && <ErrorMessage message="Messages could not be loaded." />}
        {messages.data?.length === 0 && <p>No raw messages ingested yet.</p>}
        <div className="card-list">
          {messages.data?.map((msg) => (
            <article className="card" key={msg.id} data-testid={`raw-message-${msg.id}`}>
              <strong>{msg.subject || "(No Subject)"}</strong>
              <p>From: {msg.sender} · {msg.internal_date}</p>
              {msg.snippet && <p className="snippet">{msg.snippet}</p>}
              <span className={`status status-${msg.status}`}>{msg.status}</span>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function MatchingPanel({ planId }: { planId: string }) {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [classFilter, setClassFilter] = useState("");
  const [autoLinkExact, setAutoLinkExact] = useState(false);

  const matches = useQuery({
    queryKey: ["plans", planId, "matching", statusFilter, classFilter],
    queryFn: () => getMatches(planId, statusFilter || undefined, classFilter || undefined),
  });

  const invalidate = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["plans", planId, "matching"] }),
      queryClient.invalidateQueries({ queryKey: ["plans", planId, "transactions"] }),
      queryClient.invalidateQueries({ queryKey: ["plans", planId, "watchers", "candidates"] }),
      queryClient.invalidateQueries({ queryKey: ["plans", planId, "accounts"] }),
    ]);

  const evalMutation = useMutation({
    mutationFn: () => evaluateMatches(planId, { auto_link_exact: autoLinkExact }),
    onSuccess: invalidate,
  });

  const acceptMutation = useMutation({
    mutationFn: (matchId: string) => acceptMatch(planId, matchId),
    onSuccess: invalidate,
  });

  const rejectMutation = useMutation({
    mutationFn: (matchId: string) => rejectMatch(planId, matchId),
    onSuccess: invalidate,
  });

  const unlinkMutation = useMutation({
    mutationFn: (matchId: string) => unlinkMatch(planId, matchId),
    onSuccess: invalidate,
  });

  return (
    <section className="panel" aria-labelledby="matching-heading" data-testid="matching-panel">
      <div className="account-heading">
        <div>
          <h2 id="matching-heading">Matching &amp; Deduplication</h2>
          <p className="field-help">
            Four-way deterministic classification across manual postings, watcher notices, and statement records.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <label style={{ display: "flex", flexDirection: "row", alignItems: "center", gap: "0.35rem", fontWeight: "normal", fontSize: "0.85rem" }}>
            <input
              type="checkbox"
              checked={autoLinkExact}
              onChange={(e) => setAutoLinkExact(e.target.checked)}
              data-testid="auto-link-exact-checkbox"
            />
            Auto-link EXACT matches
          </label>
          <button
            type="button"
            disabled={evalMutation.isPending}
            onClick={() => evalMutation.mutate()}
            data-testid="evaluate-matches-button"
          >
            {evalMutation.isPending ? "Evaluating…" : "Evaluate Matches"}
          </button>
        </div>
      </div>

      <div className="match-filters" style={{ marginTop: "1rem" }}>
        <label style={{ display: "flex", flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
          Classification:
          <select
            value={classFilter}
            onChange={(e) => setClassFilter(e.target.value)}
            data-testid="classification-filter"
          >
            <option value="">All Classifications</option>
            <option value="EXACT_MATCH">EXACT_MATCH</option>
            <option value="HIGH_CONFIDENCE_MATCH">HIGH_CONFIDENCE_MATCH</option>
            <option value="POSSIBLE_MATCH">POSSIBLE_MATCH</option>
            <option value="NEW_TRANSACTION">NEW_TRANSACTION</option>
          </select>
        </label>

        <label style={{ display: "flex", flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
          Status:
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            data-testid="status-filter"
          >
            <option value="">All Statuses</option>
            <option value="suggested">suggested</option>
            <option value="accepted">accepted</option>
            <option value="rejected">rejected</option>
            <option value="unlinked">unlinked</option>
          </select>
        </label>
      </div>

      {evalMutation.isError && <ErrorMessage message={evalMutation.error.message} />}
      {acceptMutation.isError && <ErrorMessage message={acceptMutation.error.message} />}
      {rejectMutation.isError && <ErrorMessage message={rejectMutation.error.message} />}
      {unlinkMutation.isError && <ErrorMessage message={unlinkMutation.error.message} />}

      <div className="card-list" data-testid="matching-list">
        {matches.isPending && <p>Loading matches…</p>}
        {matches.isError && <ErrorMessage message="Matches could not be loaded." />}
        {matches.data?.length === 0 && <p>No matches found. Click &quot;Evaluate Matches&quot; to discover potential links.</p>}
        {matches.data?.map((m) => {
          const classClass =
            m.classification === "EXACT_MATCH"
              ? "status-exact"
              : m.classification === "HIGH_CONFIDENCE_MATCH"
              ? "status-high"
              : m.classification === "POSSIBLE_MATCH"
              ? "status-possible"
              : "status-new";

          return (
            <article className="card match-card" key={m.id} data-testid={`match-card-${m.id}`}>
              <div className="account-heading">
                <div>
                  <span className={`status ${classClass}`} data-testid={`match-classification-${m.id}`}>
                    {m.classification}
                  </span>
                  <span style={{ marginLeft: "0.5rem", fontSize: "0.85rem", color: "#64748b" }}>
                    Confidence: <strong>{m.confidence_score}</strong>
                  </span>
                </div>
                <span className={`status status-${m.status}`} data-testid={`match-status-${m.id}`}>
                  {m.status}
                </span>
              </div>

              <div className="match-comparison">
                <div>
                  <h5>
                    {m.candidate
                      ? `Candidate (${m.candidate.candidate_type})`
                      : m.statement_row
                      ? "Statement Row"
                      : "Source Entity"}
                  </h5>
                  {m.candidate && (
                    <>
                      <p>
                        <strong>{m.candidate.reported_amount} {m.candidate.reported_currency}</strong>
                        {m.candidate.merchant && ` · ${m.candidate.merchant}`}
                      </p>
                      <p style={{ fontSize: "0.85rem", color: "#64748b" }}>
                        {m.candidate.subject || m.candidate.glosa}
                      </p>
                      <p style={{ fontSize: "0.8rem", color: "#64748b" }}>
                        Date: {m.candidate.event_at ? m.candidate.event_at.slice(0, 19).replace("T", " ") : `Notice: ${m.candidate.notification_at?.slice(0, 19).replace("T", " ")}`}
                      </p>
                      {m.candidate.candidate_type === "banco_ganadero" && !m.candidate.event_at && (
                        <p style={{ fontSize: "0.8rem", color: "#92400e" }}>
                          Notice has notification time only; event time enriched on statement link.
                        </p>
                      )}
                    </>
                  )}
                  {m.statement_row && (
                    <>
                      <p>
                        <strong>Row #{m.statement_row.source_row_index + 1}: {m.statement_row.signed_amount}</strong>
                      </p>
                      <p style={{ fontSize: "0.85rem", color: "#64748b" }}>
                        {m.statement_row.description}
                      </p>
                      <p style={{ fontSize: "0.8rem", color: "#64748b" }}>
                        Tx #{m.statement_row.transaction_number} · Date: {m.statement_row.event_at.slice(0, 19).replace("T", " ")}
                      </p>
                    </>
                  )}
                </div>

                <div>
                  <h5>Target Transaction</h5>
                  {m.transaction ? (
                    <>
                      <p>
                        <strong>{m.transaction.type} {m.transaction.amount} {m.transaction.currency_code}</strong>
                      </p>
                      <p style={{ fontSize: "0.85rem", color: "#64748b" }}>
                        {m.transaction.merchant || "No merchant"} · {m.transaction.memo || "No memo"}
                      </p>
                      <p style={{ fontSize: "0.8rem", color: "#64748b" }}>
                        Date: {m.transaction.event_at.slice(0, 19).replace("T", " ")} · Source: {m.transaction.source}
                      </p>
                    </>
                  ) : (
                    <p style={{ color: "#64748b", fontStyle: "italic" }}>
                      No existing transaction matched (New Transaction)
                    </p>
                  )}
                </div>
              </div>

              {m.classification === "POSSIBLE_MATCH" && (
                <p className="field-help" style={{ color: "#92400e", marginBottom: "0.5rem" }}>
                  ⚠️ Inconclusive match — requires explicit human review and will not be auto-merged.
                </p>
              )}

              <details className="match-signals" data-testid={`match-signals-${m.id}`}>
                <summary style={{ cursor: "pointer", fontWeight: 600 }}>Signals and Provenance</summary>
                <div style={{ padding: "0.5rem 0" }}>
                  <pre style={{ margin: 0, fontSize: "0.8rem", background: "#f1f5f9", padding: "0.5rem", borderRadius: "0.35rem", overflowX: "auto" }}>
                    {JSON.stringify(m.signals, null, 2)}
                  </pre>
                </div>
              </details>

              <div className="card-actions" style={{ marginTop: "0.75rem" }}>
                {m.status === "suggested" && m.transaction && (
                  <>
                    <button
                      type="button"
                      disabled={acceptMutation.isPending}
                      onClick={() => acceptMutation.mutate(m.id)}
                      data-testid={`accept-match-${m.id}`}
                    >
                      {acceptMutation.isPending ? "Accepting…" : "Accept Match"}
                    </button>
                    <button
                      type="button"
                      disabled={rejectMutation.isPending}
                      onClick={() => rejectMutation.mutate(m.id)}
                      data-testid={`reject-match-${m.id}`}
                    >
                      {rejectMutation.isPending ? "Rejecting…" : "Reject"}
                    </button>
                  </>
                )}

                {m.status === "accepted" && (
                  <button
                    type="button"
                    disabled={unlinkMutation.isPending}
                    onClick={() => unlinkMutation.mutate(m.id)}
                    data-testid={`unlink-match-${m.id}`}
                  >
                    {unlinkMutation.isPending ? "Unlinking…" : "Unlink Match"}
                  </button>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function TaxonomyPanel({ planId }: { planId: string }) {
  const queryClient = useQueryClient();
  const groups = useQuery({
    queryKey: ["plans", planId, "category-groups"],
    queryFn: () => getCategoryGroups(planId),
  });
  const categories = useQuery({
    queryKey: ["plans", planId, "categories"],
    queryFn: () => getCategories(planId),
  });
  const tags = useQuery({
    queryKey: ["plans", planId, "tags"],
    queryFn: () => getTags(planId),
  });
  const [groupName, setGroupName] = useState("");
  const [categoryName, setCategoryName] = useState("");
  const [tagName, setTagName] = useState("");
  const invalidate = (key: string) => queryClient.invalidateQueries({
    queryKey: ["plans", planId, key],
  });
  const createGroupMutation = useMutation({
    mutationFn: () => createCategoryGroup(planId, newClientId(), groupName),
    onSuccess: () => { setGroupName(""); void invalidate("category-groups"); },
  });
  const createCategoryMutation = useMutation({
    mutationFn: () => createCategory(planId, newClientId(), { name: categoryName }),
    onSuccess: () => { setCategoryName(""); void invalidate("categories"); },
  });
  const createTagMutation = useMutation({
    mutationFn: () => createTag(planId, newClientId(), tagName),
    onSuccess: () => { setTagName(""); void invalidate("tags"); },
  });
  return (
    <section className="panel" aria-labelledby="taxonomy-heading">
      <h2 id="taxonomy-heading">Categories and Tags</h2>
      <div className="taxonomy-grid">
        <form onSubmit={(event) => { event.preventDefault(); createGroupMutation.mutate(); }}>
          <label>Category Group<input value={groupName} onChange={(event) => setGroupName(event.target.value)} required /></label>
          <button type="submit" disabled={createGroupMutation.isPending}>Add Group</button>
        </form>
        <form onSubmit={(event) => { event.preventDefault(); createCategoryMutation.mutate(); }}>
          <label>Category<input value={categoryName} onChange={(event) => setCategoryName(event.target.value)} required /></label>
          <button type="submit" disabled={createCategoryMutation.isPending}>Add Category</button>
        </form>
        <form onSubmit={(event) => { event.preventDefault(); createTagMutation.mutate(); }}>
          <label>Tag<input value={tagName} onChange={(event) => setTagName(event.target.value)} required /></label>
          <button type="submit" disabled={createTagMutation.isPending}>Add Tag</button>
        </form>
      </div>
      <div className="taxonomy-lists">
        <div><h3>Groups</h3>{groups.data?.map((group) => <TaxonomyItem key={group.id} label={group.name} status={group.status} protectedItem={false} onRename={(name) => renameCategoryGroup(planId, group.id, name).then(() => invalidate("category-groups"))} onArchive={() => archiveCategoryGroup(planId, group.id).then(() => invalidate("category-groups"))} />)}</div>
        <div><h3>Categories</h3>{categories.data?.map((category) => <TaxonomyItem key={category.id} label={category.name} status={category.status} protectedItem={category.is_pending} onRename={(name) => renameCategory(planId, category.id, { name }).then(() => invalidate("categories"))} onArchive={() => archiveCategory(planId, category.id).then(() => invalidate("categories"))} />)}</div>
        <div><h3>Tags</h3>{tags.data?.map((tag) => <TaxonomyItem key={tag.id} label={tag.name} status={tag.status} protectedItem={false} onRename={(name) => renameTag(planId, tag.id, name).then(() => invalidate("tags"))} onArchive={() => archiveTag(planId, tag.id).then(() => invalidate("tags"))} />)}</div>
      </div>
    </section>
  );
}

function TaxonomyItem({ label, status, protectedItem, onRename, onArchive }: { label: string; status: string; protectedItem: boolean; onRename: (name: string) => Promise<unknown>; onArchive: () => Promise<unknown> }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(label);
  return <div className="taxonomy-item"><div>{editing ? <input aria-label={`Rename ${label}`} value={name} onChange={(event) => setName(event.target.value)} /> : <strong>{label}</strong>} <span>{protectedItem ? "protected" : status}</span></div>{!protectedItem && status === "active" && <div className="card-actions">{editing ? <><button type="button" onClick={() => onRename(name).then(() => setEditing(false))}>Save</button><button type="button" onClick={() => setEditing(false)}>Cancel</button></> : <button type="button" onClick={() => setEditing(true)}>Rename</button>}<button type="button" onClick={() => void onArchive()}>Archive</button></div>}</div>;
}

function parseOptionalJson(value: string, field: string): Record<string, unknown> | undefined {
  if (!value.trim()) return undefined;
  try {
    const parsed: unknown = JSON.parse(value);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      throw new Error(`${field} must be a JSON object.`);
    }
    return parsed as Record<string, unknown>;
  } catch (error) {
    if (error instanceof Error && error.message.endsWith("must be a JSON object.")) {
      throw error;
    }
    throw new Error(`${field} must be valid JSON.`);
  }
}

function TransactionPanel({ planId, accounts, categories }: { planId: string; accounts: Account[]; categories: Category[] }) {
  const queryClient = useQueryClient();
  const transactions = useQuery({ queryKey: ["plans", planId, "transactions"], queryFn: () => getTransactions(planId) });
  const tags = useQuery({ queryKey: ["plans", planId, "tags"], queryFn: () => getTags(planId) });
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? "");
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const [type, setType] = useState<Transaction["type"]>("expense");
  const [eventAt, setEventAt] = useState(new Date().toISOString().slice(0, 16));
  const [merchant, setMerchant] = useState("");
  const [memo, setMemo] = useState("");
  const [photoReference, setPhotoReference] = useState("");
  const [locationJson, setLocationJson] = useState("");
  const [sourceMetadataJson, setSourceMetadataJson] = useState("");
  const [provenanceJson, setProvenanceJson] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [correctionAmount, setCorrectionAmount] = useState("");
  const ordinaryTransactions = (transactions.data ?? []).filter((item): item is Transaction => !("legs" in item));
  const selected = ordinaryTransactions.find((transaction) => transaction.id === selectedId) ?? null;
  useEffect(() => {
    if (!accountId && accounts[0]) setAccountId(accounts[0].id);
  }, [accountId, accounts]);
  const invalidateLedgerProjections = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["plans", planId, "transactions"] }),
      queryClient.invalidateQueries({ queryKey: ["plans", planId, "accounts"] }),
      queryClient.invalidateQueries({ queryKey: ["plans", planId, "budget"] }),
    ]);
  };
  const postMutation = useMutation({
    mutationFn: () => {
      const account = accounts.find((item) => item.id === accountId);
      if (!account) throw new Error("Select an active Account.");
      return createTransaction(planId, newClientId(), {
        type, account_id: accountId, amount, currency_code: account.currency_code,
        event_at: new Date(eventAt).toISOString(), category_id: categoryId || undefined,
        merchant: merchant || undefined, memo: memo || undefined,
        photo_reference: photoReference || undefined,
        tags: selectedTags,
        location: parseOptionalJson(locationJson, "Location"),
        source_metadata: parseOptionalJson(sourceMetadataJson, "Source metadata"),
        provenance: parseOptionalJson(provenanceJson, "Provenance"),
      });
    },
    onSuccess: async () => { await invalidateLedgerProjections(); setAmount(""); setMerchant(""); setMemo(""); setPhotoReference(""); setLocationJson(""); setSourceMetadataJson(""); setProvenanceJson(""); setSelectedTags([]); },
  });
  const correctionMutation = useMutation({
    mutationFn: () => selected ? correctTransaction(planId, selected.id, newClientId(), { amount: correctionAmount }) : Promise.reject(new Error("Select a Transaction.")),
    onSuccess: async () => { await invalidateLedgerProjections(); await queryClient.invalidateQueries({ queryKey: ["plans", planId, "transactions", selectedId, "corrections"] }); },
  });
  const corrections = useQuery({
    queryKey: ["plans", planId, "transactions", selectedId, "corrections"],
    queryFn: () => getTransactionCorrections(planId, selectedId ?? ""),
    enabled: Boolean(selectedId),
  });
  const aiSuggestions = useQuery({
    queryKey: ["plans", planId, "ai", "suggestions"],
    queryFn: () => getAISuggestions(planId),
  });

  const suggestTxMutation = useMutation({
    mutationFn: (transactionId: string) => generateTransactionSuggestion(planId, transactionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["plans", planId, "ai", "suggestions"] });
    },
  });

  const acceptAISuggestionMutation = useMutation({
    mutationFn: (suggestionId: string) => acceptAISuggestion(planId, suggestionId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "ai", "suggestions"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", planId, "transactions"] }),
      ]);
    },
  });

  const rejectAISuggestionMutation = useMutation({
    mutationFn: ({ suggestionId, reason }: { suggestionId: string; reason?: string }) =>
      rejectAISuggestion(planId, suggestionId, reason),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["plans", planId, "ai", "suggestions"] });
    },
  });

  return (
    <section className="panel" aria-labelledby="transactions-heading">
      <h2 id="transactions-heading">Manual Transactions</h2>
      <form className="form-grid" onSubmit={(event) => { event.preventDefault(); postMutation.mutate(); }}>
        <label>Type<select value={type} onChange={(event) => setType(event.target.value as Transaction["type"])}><option value="expense">Expense</option><option value="income">Income</option></select></label>
        <label>Account<select value={accountId} onChange={(event) => setAccountId(event.target.value)}>{accounts.filter((account) => account.status === "active").map((account) => <option key={account.id} value={account.id}>{account.name} · {account.currency_code}</option>)}</select></label>
        <label>Amount (exact decimal string)<input inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} required /></label>
        <p className="field-help">Use an exact decimal string in {accounts.find((account) => account.id === accountId)?.currency_code ?? "the Account currency"}; floats are rejected.</p>
        <label>Event timestamp<input type="datetime-local" value={eventAt} onChange={(event) => setEventAt(event.target.value)} required /></label>
        <label>Category<select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}><option value="">Pendientes</option>{categories.filter((category) => category.status === "active").map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
        <label>Merchant<input value={merchant} onChange={(event) => setMerchant(event.target.value)} /></label>
        <label>Memo<input value={memo} onChange={(event) => setMemo(event.target.value)} /></label>
        <label>Photo reference (opaque)<input value={photoReference} onChange={(event) => setPhotoReference(event.target.value)} /></label>
        <label>Location JSON<input value={locationJson} onChange={(event) => setLocationJson(event.target.value)} placeholder='{"city":"La Paz"}' /></label>
        <label>Source metadata JSON<input value={sourceMetadataJson} onChange={(event) => setSourceMetadataJson(event.target.value)} placeholder="{}" /></label>
        <label>Provenance JSON<input value={provenanceJson} onChange={(event) => setProvenanceJson(event.target.value)} placeholder="{}" /></label>
        <fieldset className="tag-fieldset"><legend>Tags</legend>{tags.data?.filter((tag) => tag.status === "active").map((tag) => <label key={tag.id}><input type="checkbox" checked={selectedTags.includes(tag.id)} onChange={(event) => setSelectedTags((current) => event.target.checked ? [...current, tag.id] : current.filter((id) => id !== tag.id))} />{tag.name}</label>)}</fieldset>
        <button type="submit" disabled={postMutation.isPending || !accountId}>{postMutation.isPending ? "Posting…" : "Post"}</button>
      </form>
      {postMutation.isError && <ErrorMessage message={postMutation.error.message} />}
      <div className="card-list">
        {ordinaryTransactions.map((transaction) => {
          const txSuggestions = aiSuggestions.data?.filter(
            (s) => s.transaction_id === transaction.id && (s.status === "suggested" || s.status === "quarantined")
          );
          return (
            <article className="card" key={transaction.id} data-testid={`transaction-card-${transaction.id}`}>
              <strong>{transaction.type} {transaction.amount} {transaction.currency_code}</strong>
              <p>{transaction.merchant || "No merchant"} · {transaction.memo || "No memo"}</p>
              <p>Category: {categories.find((category) => category.id === transaction.category_id)?.name ?? "Pendientes"}</p>

              {txSuggestions && txSuggestions.length > 0 && (
                <div
                  className="ai-suggestion-badge"
                  data-testid={`ai-suggestion-transaction-${transaction.id}`}
                  style={{
                    margin: "0.5rem 0",
                    padding: "0.5rem",
                    background: "#f0fdf4",
                    border: "1px solid #bbf7d0",
                    borderRadius: "4px",
                  }}
                >
                  {txSuggestions.map((s) => {
                    const catName = categories.find((cat) => cat.id === s.suggested_category_id)?.name;
                    return (
                      <div key={s.id} data-testid={`ai-tx-suggestion-item-${s.id}`}>
                        <span
                          className="status"
                          style={{
                            background: s.status === "quarantined" ? "#fef2f2" : "#dcfce7",
                            color: s.status === "quarantined" ? "#991b1b" : "#166534",
                          }}
                        >
                          {s.status === "quarantined" ? "AI Quarantined" : "AI Suggestion"}
                        </span>
                        {s.status === "suggested" && (
                          <p style={{ margin: "0.25rem 0", fontSize: "0.9rem" }}>
                            {catName && <span>Suggested Category: <strong>{catName}</strong> · </span>}
                            {s.suggested_merchant && <span>Merchant: <strong>{s.suggested_merchant}</strong> · </span>}
                            {s.confidence && <span>Confidence: {(Number(s.confidence) * 100).toFixed(0)}%</span>}
                          </p>
                        )}
                        {s.reasoning && (
                          <p className="field-help" style={{ margin: "0.25rem 0" }}>
                            {s.reasoning}
                          </p>
                        )}
                        {s.status === "suggested" && (
                          <div className="card-actions" style={{ marginTop: "0.25rem" }}>
                            <button
                              type="button"
                              data-testid={`accept-ai-tx-suggestion-${s.id}`}
                              disabled={acceptAISuggestionMutation.isPending}
                              onClick={() => acceptAISuggestionMutation.mutate(s.id)}
                            >
                              Apply Suggestion
                            </button>
                            <button
                              type="button"
                              data-testid={`reject-ai-tx-suggestion-${s.id}`}
                              disabled={rejectAISuggestionMutation.isPending}
                              onClick={() => rejectAISuggestionMutation.mutate({ suggestionId: s.id })}
                            >
                              Dismiss
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="card-actions">
                <button
                  type="button"
                  onClick={() => {
                    setSelectedId(transaction.id);
                    setCorrectionAmount(transaction.amount);
                  }}
                >
                  View detail and correct
                </button>
                <button
                  type="button"
                  data-testid={`ai-suggest-transaction-${transaction.id}`}
                  disabled={suggestTxMutation.isPending}
                  onClick={() => suggestTxMutation.mutate(transaction.id)}
                >
                  {suggestTxMutation.isPending ? "Analyzing…" : "Suggest Category (AI)"}
                </button>
              </div>

              {selected?.id === transaction.id && (
                <>
                  <div className="transaction-detail">
                    <p>Account {transaction.account_id}</p>
                    <p>
                      Category{" "}
                      {categories.find((category) => category.id === transaction.category_id)?.name ??
                        transaction.category_id}
                    </p>
                    <p>Event {transaction.event_at}</p>
                  </div>
                  <form
                    className="inline-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      correctionMutation.mutate();
                    }}
                  >
                    <label>
                      Replacement amount
                      <input
                        value={correctionAmount}
                        onChange={(event) => setCorrectionAmount(event.target.value)}
                        required
                      />
                    </label>
                    <button type="submit" disabled={correctionMutation.isPending}>
                      {correctionMutation.isPending ? "Saving…" : "Save correction"}
                    </button>
                    <button type="button" onClick={() => setSelectedId(null)}>
                      Close
                    </button>
                  </form>
                  <div>
                    <strong>Correction history</strong>
                    {corrections.isPending && <p>Loading correction history…</p>}
                    {corrections.data?.map((correction) => (
                      <p key={correction.id}>
                        #{correction.correction_sequence}: {String(correction.before_snapshot.amount)} →{" "}
                        {String(correction.after_snapshot.amount)}
                      </p>
                    ))}
                  </div>
                </>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function BudgetPanel({ planId, categories }: { planId: string; categories: Category[] }) {
  const queryClient = useQueryClient();
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const summary = useQuery({ queryKey: ["plans", planId, "budget", month], queryFn: () => getMonthlySummary(planId, month) });
  const assignment = useMutation({ mutationFn: () => createAssignment(planId, newClientId(), { category_id: categoryId, month, amount }), onSuccess: () => { setAmount(""); void queryClient.invalidateQueries({ queryKey: ["plans", planId, "budget", month] }); } });
  return <section className="panel" aria-labelledby="budget-heading"><h2 id="budget-heading">Budget month</h2><label>Month<input type="month" value={month} onChange={(event) => setMonth(event.target.value)} /></label>{summary.data && <><p>Ready to Assign <strong>{summary.data.ready_to_assign} {summary.data.currency}</strong></p><form className="inline-form" onSubmit={(event) => { event.preventDefault(); assignment.mutate(); }}><label>Category<select value={categoryId} onChange={(event) => setCategoryId(event.target.value)} required><option value="">Select category</option>{categories.filter((category) => category.status === "active").map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label><label>Assignment (exact decimal string)<input value={amount} onChange={(event) => setAmount(event.target.value)} required /></label><button type="submit">Assign</button></form><div className="card-list">{summary.data.categories.map((envelope) => <article className="card" key={envelope.category_id}><strong>{categories.find((category) => category.id === envelope.category_id)?.name}</strong><p>Assigned {envelope.assigned} · Activity {envelope.activity} · Available {envelope.available} {envelope.currency}</p>{envelope.unconverted_by_currency.map((item) => <p key={item.currency} className="unconverted">Unconverted {item.currency}: {item.amount}</p>)}</article>)}</div>{summary.data.unconverted_by_currency.map((item) => <p className="unconverted" key={item.currency}>Unconverted {item.currency}: {item.amount}</p>)}</>}</section>;
}

function TransferPanel({ planId, accounts }: { planId: string; accounts: Account[] }) {
  const queryClient = useQueryClient();
  const currencies = useCurrencies();
  const transfers = useQuery({ queryKey: ["plans", planId, "transfers"], queryFn: () => getTransfers(planId) });
  const active = accounts.filter((account) => account.status === "active");
  const [source, setSource] = useState(active[0]?.id ?? "");
  const [destination, setDestination] = useState(active[1]?.id ?? "");
  const [outbound, setOutbound] = useState(""); const [inbound, setInbound] = useState("");
  const [eventAt, setEventAt] = useState(new Date().toISOString().slice(0, 16));
  const [rateSource, setRateSource] = useState(""); const [memo, setMemo] = useState("");
  const [reversalReason, setReversalReason] = useState("");
  const [reversalAt, setReversalAt] = useState(new Date().toISOString().slice(0, 16));
  const sourceAccount = active.find((item) => item.id === source); const destinationAccount = active.find((item) => item.id === destination);
  useEffect(() => {
    if (!active.some((account) => account.id === source)) setSource(active[0]?.id ?? "");
    if (!active.some((account) => account.id === destination) || destination === source) setDestination(active.find((account) => account.id !== source)?.id ?? "");
  }, [active, source, destination]);
  const cross = Boolean(sourceAccount && destinationAccount && sourceAccount.currency_code !== destinationAccount.currency_code);
  const validateAmount = (value: string, account: Account | undefined) => {
    const places = currencies.data?.find((currency) => currency.code === account?.currency_code)?.decimal_places;
    const [whole, fraction = ""] = value.split(".");
    const positive = /^\d+(?:\.\d+)?$/.test(value) && /[1-9]/.test(`${whole}${fraction}`);
    if (!account || places === undefined || !positive || fraction.length > places) throw new Error("Use a positive exact amount at the selected Account currency scale.");
  };
  const refresh = async () => { await Promise.all([queryClient.invalidateQueries({ queryKey: ["plans", planId, "transactions"] }), queryClient.invalidateQueries({ queryKey: ["plans", planId, "transfers"] }), queryClient.invalidateQueries({ queryKey: ["plans", planId, "accounts"] }), queryClient.invalidateQueries({ queryKey: ["plans", planId, "budget"] })]); };
  const create = useMutation({ mutationFn: () => { validateAmount(outbound, sourceAccount); validateAmount(inbound, destinationAccount); if (!cross && outbound !== inbound) throw new Error("Same-currency originals must match exactly."); if (cross && !rateSource.trim()) throw new Error("Cross-currency transfers require rate-source evidence."); return createTransfer(planId, newClientId(), { source_account_id: source, destination_account_id: destination, outbound_amount: outbound, inbound_amount: inbound, event_at: new Date(eventAt).toISOString(), ...(cross ? { rate_source: rateSource } : {}), memo: memo || null, provenance: {} }); }, onSuccess: refresh });
  const reversal = useMutation({ mutationFn: (transfer: Transfer) => { if (!reversalReason.trim()) throw new Error("A reversal reason is required."); return reverseTransfer(planId, transfer.id, newClientId(), { event_at: new Date(reversalAt).toISOString(), reversal_reason: reversalReason, memo: null, provenance: {} }); }, onSuccess: refresh });
  return (
    <section className="panel" aria-labelledby="transfers-heading">
      <h2 id="transfers-heading">Transfers</h2>
      {active.length < 2 ? <p className="field-help">Create two active Accounts to make a Transfer.</p> : <form className="form-grid" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
        <label>From<select value={source} onChange={(event) => setSource(event.target.value)}>{active.map((account) => <option key={account.id} value={account.id}>{account.name} · {account.currency_code}</option>)}</select></label>
        <label>To<select value={destination} onChange={(event) => setDestination(event.target.value)}>{active.filter((account) => account.id !== source).map((account) => <option key={account.id} value={account.id}>{account.name} · {account.currency_code}</option>)}</select></label>
        <label>Sent (exact)<input required value={outbound} onChange={(event) => setOutbound(event.target.value)} /></label>
        <label>Received (exact)<input required value={inbound} onChange={(event) => setInbound(event.target.value)} /></label>
        <label>Timestamp<input type="datetime-local" required value={eventAt} onChange={(event) => setEventAt(event.target.value)} /></label>
        {cross ? <label>Rate source evidence<input required value={rateSource} onChange={(event) => setRateSource(event.target.value)} /></label> : <p className="field-help">Same currency amounts must match; rate is exactly 1 and has no source.</p>}
        <label>Memo<input value={memo} onChange={(event) => setMemo(event.target.value)} /></label>
        {cross ? <p className="field-help">Evidence: {outbound || "sent"} {sourceAccount?.currency_code} / {inbound || "received"} {destinationAccount?.currency_code}</p> : null}
        <button disabled={create.isPending || !source || !destination || source === destination}>{create.isPending ? "Posting…" : "Create Transfer"}</button>
      </form>}
      {create.isError ? <ErrorMessage message={create.error.message} /> : null}
      <div className="card-list">{transfers.data?.map((transfer) => (
        <article className="card" key={transfer.id}>
          <strong>Transfer {transfer.outbound_amount} {transfer.outbound_currency_code} → {transfer.inbound_amount} {transfer.inbound_currency_code}</strong>
          <p>Event {transfer.event_at}</p>
          <p>From {accounts.find((account) => account.id === transfer.source_account_id)?.name ?? transfer.source_account_id} ({transfer.source_account_id}) to {accounts.find((account) => account.id === transfer.destination_account_id)?.name ?? transfer.destination_account_id} ({transfer.destination_account_id})</p>
          <p>Rate {transfer.rate}{transfer.rate_source ? ` · ${transfer.rate_source}` : ""}</p>
          <p>{transfer.memo || "No memo"} · {transfer.legs.map((leg) => `${leg.role} leg ${leg.id}, transaction ${leg.transaction_id}, movement ${leg.movement_id}`).join("; ")}</p>
          {transfer.reversal_reason ? <p>Reversal reason: {transfer.reversal_reason}</p> : null}
          {transfer.reverses_transfer_id ? <p>Reverses transfer {transfer.reverses_transfer_id}</p> : null}
          {!transfer.reverses_transfer_id ? <div className="inline-form"><label>Reversal timestamp<input type="datetime-local" value={reversalAt} onChange={(event) => setReversalAt(event.target.value)} /></label><label>Reversal reason<input value={reversalReason} onChange={(event) => setReversalReason(event.target.value)} required /></label><button type="button" disabled={reversal.isPending} onClick={() => reversal.mutate(transfer)}>Reverse transfer</button></div> : null}
        </article>
      ))}</div>
      {reversal.isError ? <ErrorMessage message={reversal.error.message} /> : null}
    </section>
  );
}

function LedgerScreen() {
  const { planId } = useParams<{ planId: string }>();
  const accounts = useQuery({ queryKey: ["plans", planId, "accounts"], queryFn: () => getAccounts(planId ?? ""), enabled: Boolean(planId) });
  const categories = useQuery({ queryKey: ["plans", planId, "categories"], queryFn: () => getCategories(planId ?? ""), enabled: Boolean(planId) });
  if (!planId) return <Navigate to="/plans" replace />;
  return (
    <main className="page">
      <header className="page-header">
        <div>
          <Link to={`/plans/${planId}/accounts`}>← Accounts</Link>{" "}
          <Link to={`/plans/${planId}/analytics`}>Analytics →</Link>
          <p className="eyebrow">Ledger</p>
          <h1>Ledger</h1>
          <p>Exact, Plan-scoped activity and monthly envelopes.</p>
        </div>
      </header>
      <TaxonomyPanel planId={planId} />
      <TransactionPanel planId={planId} accounts={accounts.data ?? []} categories={categories.data ?? []} />
      <TransferPanel planId={planId} accounts={accounts.data ?? []} />
      <BudgetPanel planId={planId} categories={categories.data ?? []} />
    </main>
  );
}

function AnalyticsScreen() {
  const { planId } = useParams<{ planId: string }>();
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [useCustomRange, setUseCustomRange] = useState(false);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [trendInterval, setTrendInterval] = useState<"day" | "week" | "month">("day");
  const [typeFilter, setTypeFilter] = useState<"expense" | "income" | "all">("expense");
  const [includeLocations, setIncludeLocations] = useState(false);
  const [merchantLimit, setMerchantLimit] = useState(10);
  const [goalsMonth, setGoalsMonth] = useState(new Date().toISOString().slice(0, 7));

  const plan = useQuery({
    queryKey: ["plans", planId],
    queryFn: () => getPlan(planId ?? ""),
    enabled: Boolean(planId),
  });

  const queryParams = useCustomRange && startDate && endDate
    ? { start_date: new Date(startDate).toISOString(), end_date: new Date(endDate).toISOString() }
    : { month };

  const summary = useQuery({
    queryKey: ["plans", planId, "analytics", "summary", queryParams],
    queryFn: () => getAnalyticsSummary(planId ?? "", queryParams),
    enabled: Boolean(planId),
  });

  const categoryBreakdown = useQuery({
    queryKey: ["plans", planId, "analytics", "categories", queryParams, typeFilter],
    queryFn: () => getCategoryBreakdown(planId ?? "", { ...queryParams, type: typeFilter }),
    enabled: Boolean(planId),
  });

  const merchantRankings = useQuery({
    queryKey: ["plans", planId, "analytics", "merchants", queryParams, merchantLimit],
    queryFn: () => getMerchantRankings(planId ?? "", { ...queryParams, limit: merchantLimit }),
    enabled: Boolean(planId),
  });

  const tagBreakdown = useQuery({
    queryKey: ["plans", planId, "analytics", "tags", queryParams, typeFilter],
    queryFn: () => getTagBreakdown(planId ?? "", { ...queryParams, type: typeFilter }),
    enabled: Boolean(planId),
  });

  const cashflowTrends = useQuery({
    queryKey: ["plans", planId, "analytics", "trends", queryParams, trendInterval],
    queryFn: () => getCashflowTrends(planId ?? "", { ...queryParams, interval: trendInterval }),
    enabled: Boolean(planId),
  });

  const activityHeatmap = useQuery({
    queryKey: ["plans", planId, "analytics", "heatmap", queryParams, includeLocations],
    queryFn: () => getActivityHeatmap(planId ?? "", { ...queryParams, include_locations: includeLocations }),
    enabled: Boolean(planId),
  });

  const goalsAnalytics = useQuery({
    queryKey: ["plans", planId, "analytics", "goals", goalsMonth],
    queryFn: () => getGoalsAnalytics(planId ?? "", { as_of_month: goalsMonth }),
    enabled: Boolean(planId),
  });

  if (!planId) return <Navigate to="/plans" replace />;

  const currency = plan.data?.reporting_currency_code ?? "";

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <Link to={`/plans/${planId}/accounts`}>← Accounts</Link>{" "}
          <Link to={`/plans/${planId}/ledger`}>Ledger →</Link>
          <p className="eyebrow">Analytics & Insights</p>
          <h1>{plan.data?.name ?? "Plan"} Analytics</h1>
          <p>Reporting currency: {currency}</p>
        </div>
      </header>

      {/* Period & Filter Selection */}
      <section className="panel" aria-labelledby="period-heading">
        <h2 id="period-heading">Reporting Period & Controls</h2>
        <div className="form-grid">
          <label>
            Mode
            <select
              value={useCustomRange ? "custom" : "month"}
              onChange={(e) => setUseCustomRange(e.target.value === "custom")}
            >
              <option value="month">Month</option>
              <option value="custom">Custom Date Range</option>
            </select>
          </label>
          {!useCustomRange ? (
            <label>
              Month
              <input
                type="month"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                data-testid="analytics-month-input"
              />
            </label>
          ) : (
            <>
              <label>
                Start Date
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  data-testid="analytics-start-date"
                />
              </label>
              <label>
                End Date
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  data-testid="analytics-end-date"
                />
              </label>
            </>
          )}
          <label>
            Breakdown Type
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as "expense" | "income" | "all")}
            >
              <option value="expense">Expenses Only</option>
              <option value="income">Income Only</option>
              <option value="all">All Movements</option>
            </select>
          </label>
          <label>
            Trends Interval
            <select
              value={trendInterval}
              onChange={(e) => setTrendInterval(e.target.value as "day" | "week" | "month")}
            >
              <option value="day">Day</option>
              <option value="week">Week</option>
              <option value="month">Month</option>
            </select>
          </label>
          <label style={{ display: "flex", flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
            <input
              type="checkbox"
              checked={includeLocations}
              onChange={(e) => setIncludeLocations(e.target.checked)}
              data-testid="include-locations-toggle"
            />
            <span>Include Location Analytics (Consent required)</span>
          </label>
        </div>
      </section>

      {/* Summary KPI Cards */}
      <section className="panel" aria-labelledby="summary-heading">
        <h2 id="summary-heading">Summary KPIs</h2>
        {summary.isPending && <p>Loading summary metrics…</p>}
        {summary.isError && <ErrorMessage message="Failed to load summary analytics." />}
        {summary.data && (
          <>
            <div className="card-list" data-testid="summary-kpis">
              <article className="card" data-testid="kpi-income">
                <h3>Total Income</h3>
                <p><strong>{summary.data.total_income} {currency}</strong></p>
              </article>
              <article className="card" data-testid="kpi-expenses">
                <h3>Total Expenses</h3>
                <p><strong>{summary.data.total_expenses} {currency}</strong></p>
              </article>
              <article className="card" data-testid="kpi-net">
                <h3>Net Cashflow</h3>
                <p><strong>{summary.data.net_cashflow} {currency}</strong></p>
              </article>
              <article className="card" data-testid="kpi-savings-rate">
                <h3>Savings Rate</h3>
                <p><strong>{summary.data.savings_rate}%</strong></p>
              </article>
              <article className="card" data-testid="kpi-transfers">
                <h3>Transfers Excluded</h3>
                <p><strong>{summary.data.transfers_count} transfer(s)</strong></p>
                <p className="field-help">{summary.data.transfers_excluded_notice}</p>
              </article>
            </div>

            {summary.data.unconverted_totals.length > 0 && (
              <div style={{ marginTop: "1rem" }} data-testid="unconverted-summary-section">
                <h3>Unconverted Foreign Currencies</h3>
                <p className="field-help">
                  Amounts in foreign currencies are isolated to prevent misleading aggregation without explicit conversion.
                </p>
                <div className="card-list">
                  {summary.data.unconverted_totals.map((u) => (
                    <article className="card" key={u.currency_code}>
                      <strong>{u.currency_code}</strong>
                      <p>Income: {u.total_income} · Expenses: {u.total_expenses} · Net: {u.net_amount}</p>
                      <p className="field-help">{u.transaction_count} transaction(s)</p>
                    </article>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </section>

      {/* Cashflow Trends */}
      <section className="panel" aria-labelledby="trends-heading">
        <h2 id="trends-heading">Cashflow Trends ({trendInterval})</h2>
        {cashflowTrends.isPending && <p>Loading trend data…</p>}
        {cashflowTrends.isError && <ErrorMessage message="Failed to load cashflow trends." />}
        {cashflowTrends.data && (
          <div data-testid="cashflow-trends-container">
            {cashflowTrends.data.points.length === 0 ? (
              <p>No activity recorded in this period.</p>
            ) : (
              <div className="card-list">
                {cashflowTrends.data.points.map((pt) => (
                  <article className="card" key={pt.bucket_key}>
                    <strong>{pt.bucket_key}</strong>
                    <p>
                      Income: {pt.income} {currency} · Expense: {pt.expense} {currency}
                    </p>
                    <p>
                      Net: <strong>{pt.net} {currency}</strong> (Cumulative: {pt.cumulative_net} {currency})
                    </p>
                    <p className="field-help">{pt.transaction_count} transaction(s)</p>
                  </article>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      {/* Category Breakdown */}
      <section className="panel" aria-labelledby="categories-heading">
        <h2 id="categories-heading">Category & Group Breakdown</h2>
        {categoryBreakdown.isPending && <p>Loading category breakdown…</p>}
        {categoryBreakdown.isError && <ErrorMessage message="Failed to load category breakdown." />}
        {categoryBreakdown.data && (
          <div data-testid="category-breakdown-container">
            <p>Total {typeFilter}: <strong>{categoryBreakdown.data.total_amount} {currency}</strong></p>
            <div className="card-list">
              {categoryBreakdown.data.groups.map((group) => (
                <article className="card" key={group.group_id ?? "ungrouped"}>
                  <h3>{group.group_name} ({group.percentage}%)</h3>
                  <p><strong>{group.amount} {currency}</strong> · {group.transaction_count} transaction(s)</p>
                  <ul style={{ paddingLeft: "1.2rem", margin: "0.5rem 0" }}>
                    {group.categories.map((cat) => (
                      <li key={cat.category_id ?? "uncategorized"}>
                        <strong>{cat.category_name}</strong>: {cat.amount} {currency} ({cat.percentage}%)
                        {cat.unconverted_by_currency.map((u) => (
                          <span key={u.currency_code} className="unconverted"> [+{u.amount} {u.currency_code}]</span>
                        ))}
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Merchant Leaderboard */}
      <section className="panel" aria-labelledby="merchants-heading">
        <h2 id="merchants-heading">Top Merchants</h2>
        <div style={{ marginBottom: "0.8rem" }}>
          <label style={{ maxWidth: "10rem" }}>
            Top Limit
            <select
              value={merchantLimit}
              onChange={(e) => setMerchantLimit(Number(e.target.value))}
            >
              <option value={5}>Top 5</option>
              <option value={10}>Top 10</option>
              <option value={20}>Top 20</option>
            </select>
          </label>
        </div>
        {merchantRankings.isPending && <p>Loading merchant rankings…</p>}
        {merchantRankings.isError && <ErrorMessage message="Failed to load merchant rankings." />}
        {merchantRankings.data && (
          <div data-testid="merchant-rankings-container">
            {merchantRankings.data.merchants.length === 0 ? (
              <p>No merchant expenses in this period.</p>
            ) : (
              <div className="card-list">
                {merchantRankings.data.merchants.map((m, idx) => (
                  <article className="card" key={m.merchant}>
                    <strong>#{idx + 1} {m.merchant}</strong>
                    <p>Total: {m.total_amount} {currency} ({m.percentage}%)</p>
                    <p className="field-help">
                      {m.transaction_count} purchase(s) · Avg: {m.average_amount} {currency}
                    </p>
                    {m.unconverted_by_currency.map((u) => (
                      <p key={u.currency_code} className="unconverted">
                        Unconverted {u.currency_code}: {u.amount}
                      </p>
                    ))}
                  </article>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      {/* Tag Breakdown */}
      <section className="panel" aria-labelledby="tags-heading">
        <h2 id="tags-heading">Tag Breakdown</h2>
        {tagBreakdown.isPending && <p>Loading tag breakdown…</p>}
        {tagBreakdown.isError && <ErrorMessage message="Failed to load tag analytics." />}
        {tagBreakdown.data && (
          <div data-testid="tag-breakdown-container">
            <p>Total Tagged: <strong>{tagBreakdown.data.total_tagged_amount} {currency}</strong></p>
            <div className="card-list">
              {tagBreakdown.data.tags.map((t) => (
                <article className="card" key={t.tag_id}>
                  <strong>#{t.tag_name}</strong>
                  <p>{t.amount} {currency} ({t.percentage}%)</p>
                  <p className="field-help">{t.transaction_count} transaction(s)</p>
                </article>
              ))}
              <article className="card">
                <strong>Untagged Transactions</strong>
                <p>{tagBreakdown.data.untagged_amount} {currency}</p>
                <p className="field-help">{tagBreakdown.data.untagged_transaction_count} transaction(s)</p>
              </article>
            </div>
          </div>
        )}
      </section>

      {/* Activity Heatmap & Location Analytics */}
      <section className="panel" aria-labelledby="heatmap-heading">
        <h2 id="heatmap-heading">Activity Heatmap & Location Analysis</h2>
        {activityHeatmap.isPending && <p>Loading activity heatmap…</p>}
        {activityHeatmap.isError && <ErrorMessage message="Failed to load activity heatmap." />}
        {activityHeatmap.data && (
          <div data-testid="activity-heatmap-container">
            <h3>Peak Activity by Day & Hour</h3>
            <div className="card-list">
              {activityHeatmap.data.day_hour_matrix
                .filter((cell) => cell.transaction_count > 0)
                .slice(0, 10)
                .map((cell) => (
                  <article className="card" key={`${cell.day_of_week}-${cell.hour_of_day}`}>
                    <strong>{cell.day_name} at {cell.hour_of_day}:00</strong>
                    <p>{cell.transaction_count} transaction(s) · {cell.total_amount} {currency}</p>
                  </article>
                ))}
              {activityHeatmap.data.day_hour_matrix.every((c) => c.transaction_count === 0) && (
                <p>No activity recorded in this period.</p>
              )}
            </div>

            <h3 style={{ marginTop: "1rem" }}>Daily Activity</h3>
            <div className="card-list">
              {activityHeatmap.data.daily_activity
                .filter((d) => d.transaction_count > 0)
                .map((d) => (
                  <article className="card" key={d.date}>
                    <strong>{d.date}</strong>
                    <p>Total: {d.total_amount} {currency} ({d.transaction_count} txs)</p>
                    <p className="field-help">Income: {d.income} · Expenses: {d.expense}</p>
                  </article>
                ))}
            </div>

            {activityHeatmap.data.location_clusters && (
              <div style={{ marginTop: "1rem" }} data-testid="location-insights-section">
                <h3>Location Insights (Consent Granted)</h3>
                {activityHeatmap.data.location_clusters.length === 0 ? (
                  <p>No geotagged transactions found in this period.</p>
                ) : (
                  <div className="card-list">
                    {activityHeatmap.data.location_clusters.map((loc, idx) => (
                      <article className="card" key={idx}>
                        <strong>{loc.label || loc.merchant || "Location point"}</strong>
                        <p>Coordinates: {loc.latitude?.toFixed(4)}, {loc.longitude?.toFixed(4)}</p>
                        <p>Amount: {loc.amount} {loc.currency_code}</p>
                      </article>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </section>

      {/* Budget Goal Status */}
      <section className="panel" aria-labelledby="goals-heading">
        <h2 id="goals-heading">Budget Goal Health</h2>
        <div style={{ marginBottom: "0.8rem" }}>
          <label style={{ maxWidth: "12rem" }}>
            Goal Evaluation Month
            <input
              type="month"
              value={goalsMonth}
              onChange={(e) => setGoalsMonth(e.target.value)}
              data-testid="goals-month-input"
            />
          </label>
        </div>
        {goalsAnalytics.isPending && <p>Loading goal analytics…</p>}
        {goalsAnalytics.isError && <ErrorMessage message="Failed to load goal analytics." />}
        {goalsAnalytics.data && (
          <div data-testid="goals-analytics-container">
            {goalsAnalytics.data.goals.length === 0 ? (
              <p>No active categories with budget goals defined.</p>
            ) : (
              <div className="card-list">
                {goalsAnalytics.data.goals.map((g) => (
                  <article className="card" key={g.category_id}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <strong>{g.category_name} {g.group_name ? `(${g.group_name})` : ""}</strong>
                      <span
                        style={{
                          padding: "0.2rem 0.5rem",
                          borderRadius: "0.3rem",
                          fontSize: "0.75rem",
                          fontWeight: "bold",
                          textTransform: "uppercase",
                          background:
                            g.status === "completed" || g.status === "funded"
                              ? "#dcfce7"
                              : g.status === "on_track"
                              ? "#e0e7ff"
                              : "#fee2e2",
                          color:
                            g.status === "completed" || g.status === "funded"
                              ? "#166534"
                              : g.status === "on_track"
                              ? "#3730a3"
                              : "#991b1b",
                        }}
                      >
                        {g.status.replace("_", " ")}
                      </span>
                    </div>
                    <p>
                      Progress: <strong>{g.current_progress_amount}</strong> / {g.target_amount} {currency} ({g.progress_percentage}%)
                    </p>
                    <p className="field-help">
                      Goal type: {g.goal_type} · Remaining: {g.remaining_amount} {currency}
                      {g.goal_due_month ? ` · Due: ${g.goal_due_month}` : ""}
                    </p>
                  </article>
                ))}
              </div>
            )}
          </div>
        )}
      </section>
    </main>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/plans" element={<PlanScreen />} />
      <Route path="/plans/:planId/accounts" element={<AccountsScreen />} />
      <Route path="/plans/:planId/ledger" element={<LedgerScreen />} />
      <Route path="/plans/:planId/analytics" element={<AnalyticsScreen />} />
      <Route path="*" element={<Navigate to="/plans" replace />} />
    </Routes>
  );
}

export function App() {
  return <AppRoutes />;
}
