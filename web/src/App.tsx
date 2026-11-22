import { FormEvent, useEffect, useRef, useState } from "react";
import { GmailScreen } from "./GmailScreen";
import { ExpenseEntry } from "./ExpenseEntry";
import { TransactionRegister } from "./TransactionRegister";
import { WorkspaceLayout } from "./WorkspaceLayout";
import { LedgerNavigation } from "./LedgerNavigation";
import { BudgetScreen } from "./BudgetWorkspace";
import { formatMoney } from "./money";
import {
  Link,
  Navigate,
  Route,
  Routes,
  useNavigate,
  useParams,
  useSearchParams,
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
  createCategory,
  createCategoryGroup,
  createTag,
  getCategories,
  getCategoryGroups,
  getTags,
  getTransactions,
  archiveCategory,
  archiveCategoryGroup,
  archiveTag,
  renameCategory,
  renameCategoryGroup,
  renameTag,
  Transfer,
  getTransfers,
  createTransfer,
  reverseTransfer,
  ReconciliationComparison,
  confirmReconciliation,
  getReconciliations,
  previewReconciliation,
  ReconciliationStatementPayload,
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
          <a className="text-action" href="#create-plan-heading">New plan <span aria-hidden="true">↗</span></a>
        </div>
      </header>

      <section className="panel" aria-labelledby="plans-heading">
        <h2 id="plans-heading">Your Plans</h2>
        {plans.isPending && <p role="status">Loading Plans…</p>}
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
                <Link className="button" to={`/plans/${plan.id}/budget`}>Open Budget</Link>
                <Link className="button" to={`/plans/${plan.id}/accounts`}>Manage Accounts</Link>
                <button type="button" onClick={() => { setRenameId(plan.id); setRenameValue(plan.name); }}>Rename</button>
              </div>
              {renameId === plan.id && (
                <form onSubmit={(event) => submitRename(event, plan.id)} className="inline-form">
                  <label>New name<input required value={renameValue} onChange={(event) => setRenameValue(event.target.value)} /></label>
                  <button type="submit" disabled={renameMutation.isPending}>Save</button>
                  <button type="button" onClick={() => setRenameId(null)}>Cancel</button>
                </form>
              )}
            </article>
          ))}
        </div>
      </section>

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

    </main>
  );
}

function AccountCard({ account, planId }: { account: Account; planId: string }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(account.name);

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
        Balance <strong>{formatMoney(account.balance.amount, account.balance.currency)}</strong>
      </p>
      <div className="card-actions">
        <Link className="text-action" to={`/plans/${planId}/ledger?account=${account.id}`}>
          View activity <span aria-hidden="true">↗</span>
        </Link>
        {account.status === "active" && <>
          <button type="button" onClick={() => setEditing(true)}>Rename</button>
          <button
            type="button"
            onClick={() => archiveMutation.mutate()}
            disabled={archiveMutation.isPending}
          >
            {archiveMutation.isPending ? "Archiving…" : "Archive"}
          </button>
        </>}
      </div>
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
    </article>
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
    <main className="workspace-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Your financial accounts</p>
          <h1>Accounts</h1>
          <p>Reporting currency: {plan.data?.reporting_currency_code ?? "…"}</p>
        </div>
        <a className="button" href="#create-account-heading">+ New account</a>
      </header>

      <section className="panel" aria-labelledby="accounts-heading">
        <div className="section-heading">
          <h2 id="accounts-heading">Accounts</h2>
          <Link className="text-action" to={`/plans/${planId}/ledger`}>View all activity <span aria-hidden="true">↗</span></Link>
        </div>
        {accounts.isPending && <p role="status">Loading Accounts…</p>}
        {accounts.isError && <ErrorMessage message="Accounts could not be loaded." />}
        {accounts.data?.length === 0 && <p>No Accounts yet.</p>}
        <div className="card-list">
          {accounts.data?.map((account) => <AccountCard key={account.id} account={account} planId={planId} />)}
        </div>
      </section>

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

    </main>
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
        <div><h3>Categories</h3>{categories.data?.map((category) => <TaxonomyItem key={category.id} label={category.name} status={category.status} protectedItem={category.is_pending || Boolean(category.payment_account_id)} onRename={(name) => renameCategory(planId, category.id, { name }).then(() => invalidate("categories"))} onArchive={() => archiveCategory(planId, category.id).then(() => invalidate("categories"))} />)}</div>
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

function TransactionPanel({ planId, accounts, categories, entryOpen, closeEntry, onSaved }: { planId: string; accounts: Account[]; categories: Category[]; entryOpen: boolean; closeEntry: () => void; onSaved: () => void }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const accountFilter = searchParams.get("account") ?? "";
  const setAccountFilter = (accountId: string) => {
    const next = new URLSearchParams(searchParams);
    if (accountId) next.set("account", accountId);
    else next.delete("account");
    setSearchParams(next, { replace: true });
  };
  const queryClient = useQueryClient();
  const transactions = useQuery({ queryKey: ["plans", planId, "transactions"], queryFn: () => getTransactions(planId) });
  const tags = useQuery({ queryKey: ["plans", planId, "tags"], queryFn: () => getTags(planId) });
  const ordinaryTransactions = (transactions.data ?? []).filter(
    (item): item is Transaction => !("legs" in item)
      && (item.type === "income" || item.type === "expense"),
  );
  const invalidateLedgerProjections = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["plans", planId, "transactions"] }),
      queryClient.invalidateQueries({ queryKey: ["plans", planId, "accounts"] }),
      queryClient.invalidateQueries({ queryKey: ["plans", planId, "budget"] }),
    ]);
  };
  return (
    <section className="panel" aria-labelledby="transactions-heading">
      <h2 id="transactions-heading">Transactions</h2>
      <p className="section-intro">Record an expense or income. Corrections keep the original history.</p>
      {transactions.isPending && <p role="status">Loading activity…</p>}
      {transactions.isError && <ErrorMessage message="Activity could not be loaded." />}
      {transactions.isSuccess && (
        <TransactionRegister
          planId={planId}
          transactions={ordinaryTransactions}
          accounts={accounts}
          categories={categories}
          tags={tags.data ?? []}
          accountFilter={accountFilter}
          onAccountFilterChange={setAccountFilter}
          entry={entryOpen ? <ExpenseEntry key={planId} planId={planId} accounts={accounts} accountId={accountFilter || undefined}
            inRegister onClose={closeEntry} onSaved={onSaved} /> : undefined}
          onChanged={invalidateLedgerProjections}
        />
      )}
    </section>
  );
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
          <strong>Transfer {formatMoney(transfer.outbound_amount, transfer.outbound_currency_code)} → {formatMoney(transfer.inbound_amount, transfer.inbound_currency_code)}</strong>
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

type ReconciliationPreviewSnapshot = {
  generation: number;
  planId: string;
  accountId: string;
  sessionId: string;
  statementBalance: string;
  currencyCode: string;
  statementAt: string;
};

type AcceptedReconciliationPreview = ReconciliationPreviewSnapshot & {
  policy: ReconciliationComparison["policy"];
  tolerance: ReconciliationComparison["tolerance"];
  comparison: ReconciliationComparison;
};

function ReconciliationPanel({ planId, accounts }: { planId: string; accounts: Account[] }) {
  const queryClient = useQueryClient();
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? "");
  const [statementBalance, setStatementBalance] = useState("");
  const [statementAt, setStatementAt] = useState(new Date().toISOString().slice(0, 16));
  const [sessionId, setSessionId] = useState(newClientId());
  const [acceptedPreview, setAcceptedPreview] = useState<AcceptedReconciliationPreview | null>(null);
  const [previewPendingGeneration, setPreviewPendingGeneration] = useState<number | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [warningAccepted, setWarningAccepted] = useState(false);
  const previewGeneration = useRef(0);
  const selectedAccountId = accounts.some((item) => item.id === accountId)
    ? accountId
    : (accounts[0]?.id ?? "");
  const account = accounts.find((item) => item.id === selectedAccountId);
  const comparison = acceptedPreview?.comparison ?? null;
  const statementPayload = (): ReconciliationStatementPayload => {
    if (!account) throw new Error("Select an Account.");
    return {
      statement_balance: statementBalance,
      currency_code: account.currency_code,
      statement_at: new Date(`${statementAt}Z`).toISOString(),
    };
  };
  const history = useQuery({
    queryKey: ["plans", planId, "accounts", selectedAccountId, "reconciliations"],
    queryFn: () => getReconciliations(planId, selectedAccountId),
    enabled: Boolean(selectedAccountId),
  });
  const preview = useMutation({
    mutationFn: (snapshot: ReconciliationPreviewSnapshot) => previewReconciliation(
      snapshot.planId,
      snapshot.accountId,
      snapshot.sessionId,
      {
        statement_balance: snapshot.statementBalance,
        currency_code: snapshot.currencyCode,
        statement_at: snapshot.statementAt,
      },
    ),
    onSuccess: (result, snapshot) => {
      if (previewGeneration.current !== snapshot.generation) return;
      setPreviewPendingGeneration(null);
      if (result.plan_id !== snapshot.planId || result.account_id !== snapshot.accountId || result.id !== snapshot.sessionId) {
        setPreviewError("The preview response did not match the requested reconciliation snapshot.");
        return;
      }
      setAcceptedPreview({
        ...snapshot,
        policy: result.policy,
        tolerance: { ...result.tolerance },
        comparison: result,
      });
      setWarningAccepted(false);
    },
    onError: (error, snapshot) => {
      if (previewGeneration.current !== snapshot.generation) return;
      setPreviewPendingGeneration(null);
      setPreviewError(error instanceof Error ? error.message : "Preview failed.");
    },
  });
  const confirm = useMutation({
    mutationFn: ({ snapshot, accepted }: { snapshot: AcceptedReconciliationPreview; accepted: boolean }) => confirmReconciliation(
      snapshot.planId,
      snapshot.accountId,
      snapshot.sessionId,
      {
        statement_balance: snapshot.statementBalance,
        currency_code: snapshot.currencyCode,
        statement_at: snapshot.statementAt,
        warning_accepted: accepted,
      },
    ),
    onSuccess: async (_result, { snapshot }) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["plans", snapshot.planId, "accounts", snapshot.accountId, "reconciliations"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", snapshot.planId, "accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", snapshot.planId, "transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["plans", snapshot.planId, "budget"] }),
      ]);
      setSessionId(newClientId());
      setAcceptedPreview(null);
      setWarningAccepted(false);
    },
  });
  const invalidatePreview = () => {
    previewGeneration.current += 1;
    setAcceptedPreview(null);
    setPreviewPendingGeneration(null);
    setPreviewError(null);
    setWarningAccepted(false);
    preview.reset();
    confirm.reset();
  };
  useEffect(() => {
    invalidatePreview();
    return () => { previewGeneration.current += 1; };
  }, [planId, selectedAccountId, account?.currency_code]);
  const requestPreview = () => {
    const payload = statementPayload();
    const generation = previewGeneration.current + 1;
    previewGeneration.current = generation;
    setAcceptedPreview(null);
    setWarningAccepted(false);
    setPreviewError(null);
    setPreviewPendingGeneration(generation);
    preview.mutate({
      generation,
      planId,
      accountId: selectedAccountId,
      sessionId,
      statementBalance: payload.statement_balance,
      currencyCode: payload.currency_code,
      statementAt: payload.statement_at,
    });
  };
  return (
    <section className="panel" aria-labelledby="reconciliation-heading">
      <h2 id="reconciliation-heading">Reconciliation</h2>
      <form className="form-grid" onSubmit={(event) => { event.preventDefault(); requestPreview(); }}>
        <label>Reconciliation Account<select disabled={confirm.isPending} value={selectedAccountId} onChange={(event) => { setAccountId(event.target.value); invalidatePreview(); }}>{accounts.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.currency_code}{item.status === "archived" ? " · archived" : ""}</option>)}</select></label>
        <label>Statement balance (exact)<input disabled={confirm.isPending} required value={statementBalance} onChange={(event) => { setStatementBalance(event.target.value); invalidatePreview(); }} /></label>
        <label>Statement timestamp (UTC)<input disabled={confirm.isPending} type="datetime-local" required value={statementAt} onChange={(event) => { setStatementAt(event.target.value); invalidatePreview(); }} /></label>
        <button type="submit" disabled={previewPendingGeneration !== null || confirm.isPending || !selectedAccountId}>{previewPendingGeneration !== null ? "Previewing…" : "Preview reconciliation"}</button>
      </form>
      {previewError ? <ErrorMessage message={previewError} /> : null}
      {comparison ? <div className="card reconciliation-preview">
        <strong>Discrepancy {formatMoney(comparison.discrepancy.amount, comparison.discrepancy.currency)}</strong>
        <p>Statement {formatMoney(comparison.statement_balance.amount, comparison.statement_balance.currency)} · Derived as of {comparison.statement_at}: {formatMoney(comparison.derived_balance.amount, comparison.derived_balance.currency)}</p>
        <p>Policy {acceptedPreview?.policy} · tolerance {acceptedPreview ? formatMoney(acceptedPreview.tolerance.amount, acceptedPreview.tolerance.currency) : "—"}</p>
        {comparison.blocked ? <ErrorMessage message="Confirmation is blocked above the configured tolerance." /> : null}
        {comparison.requires_warning_acceptance ? <label className="warning-acceptance"><input type="checkbox" checked={warningAccepted} onChange={(event) => setWarningAccepted(event.target.checked)} />I explicitly accept this discrepancy warning.</label> : null}
        <button type="button" onClick={() => acceptedPreview && confirm.mutate({ snapshot: acceptedPreview, accepted: warningAccepted })} disabled={confirm.isPending || comparison.blocked || (comparison.requires_warning_acceptance && !warningAccepted)}>{confirm.isPending ? "Confirming…" : "Confirm reconciliation"}</button>
      </div> : null}
      {confirm.isError ? <ErrorMessage message={confirm.error.message} /> : null}
      <h3>Reconciliation history</h3>
      {history.isPending ? <p>Loading reconciliation history…</p> : null}
      <div className="card-list">{history.data?.map((item) => <article className="card" key={item.id}>
        <strong>{formatMoney(item.discrepancy.amount, item.discrepancy.currency)} discrepancy</strong>
        <p>Statement {formatMoney(item.statement_balance.amount, item.statement_balance.currency)} · derived {formatMoney(item.derived_balance.amount, item.derived_balance.currency)} · {item.statement_at}</p>
        <p>{item.adjustment_transaction_id ? `Adjustment ${item.adjustment_transaction_id}` : "Confirmed without adjustment"}</p>
      </article>)}</div>
    </section>
  );
}

function LedgerScreen() {
  const { planId } = useParams<{ planId: string }>();
  const [searchParams] = useSearchParams();
  const accounts = useQuery({ queryKey: ["plans", planId, "accounts"], queryFn: () => getAccounts(planId ?? ""), enabled: Boolean(planId) });
  const categories = useQuery({ queryKey: ["plans", planId, "categories"], queryFn: () => getCategories(planId ?? ""), enabled: Boolean(planId) });
  const [entryOpen, setEntryOpen] = useState(false);
  const [saved, setSaved] = useState(false);
  const filter = searchParams.get("account");
  useEffect(() => { setEntryOpen(false); setSaved(false); }, [filter, planId]);
  const trigger = useRef<HTMLButtonElement>(null);
  function closeEntry() { setEntryOpen(false); trigger.current?.focus(); }
  const selectedAccount = accounts.data?.find((account) => account.id === searchParams.get("account"));
  if (!planId) return <Navigate to="/plans" replace />;
  return <main className="workspace-page">
    <header className="page-header">
      <div>
        <p className="eyebrow">{selectedAccount ? "Account register" : "Plan activity"}</p>
        <h1>{selectedAccount ? selectedAccount.name : "All activity"}</h1>
        <p>{selectedAccount ? `${selectedAccount.account_type} · ${selectedAccount.currency_code} · recorded activity` : "Your recorded activity, transfers and reconciliation history."}</p>
      </div>
      <div className="entry-launcher"><button ref={trigger} type="button" className="button register-entry-button" aria-expanded={entryOpen} onClick={() => { setSaved(false); setEntryOpen(true); }}>+ Add transaction</button></div>
    </header>
    <LedgerNavigation />
      {saved && !entryOpen && <p role="status" className="completion-note">Transaction added. Balances and budget have been refreshed.</p>}
    <TransactionPanel key={planId} onSaved={() => setSaved(true)} entryOpen={entryOpen} closeEntry={closeEntry} planId={planId} accounts={accounts.data ?? []} categories={categories.data ?? []} />
    <TransferPanel planId={planId} accounts={accounts.data ?? []} />
    <ReconciliationPanel planId={planId} accounts={accounts.data ?? []} />
    <TaxonomyPanel planId={planId} />
  </main>;
}

export function AppRoutes() {
  return (
    <>
      <header className="brand-bar">
        <Link to="/plans" className="brand-link" aria-label="Numa home">numa<span aria-hidden="true">.</span></Link>
        <span className="brand-caption">Personal finance</span>
      </header>
      <Routes>
        <Route path="/plans" element={<PlanScreen />} />
        <Route path="/plans/:planId" element={<WorkspaceLayout />}>
          <Route index element={<Navigate to="budget" replace />} />
          <Route path="accounts" element={<AccountsScreen />} />
          <Route path="budget" element={<BudgetScreen />} />
          <Route path="ledger" element={<LedgerScreen />} />
          <Route path="gmail" element={<GmailScreen />} />
        </Route>
        <Route path="*" element={<Navigate to="/plans" replace />} />
      </Routes>
    </>
  );
}

export function App() {
  return <AppRoutes />;
}
