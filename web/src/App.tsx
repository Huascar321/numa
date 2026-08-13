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
      <p><Link className="button" to={`/plans/${planId}/ledger`}>Open Ledger</Link></p>
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
  const selected = transactions.data?.find((transaction) => transaction.id === selectedId) ?? null;
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
       <div className="card-list">{transactions.data?.map((transaction) => <article className="card" key={transaction.id}><strong>{transaction.type} {transaction.amount} {transaction.currency_code}</strong><p>{transaction.merchant || "No merchant"} · {transaction.memo || "No memo"}</p><button type="button" onClick={() => { setSelectedId(transaction.id); setCorrectionAmount(transaction.amount); }}>View detail and correct</button>{selected?.id === transaction.id && <><div className="transaction-detail"><p>Account {transaction.account_id}</p><p>Category {categories.find((category) => category.id === transaction.category_id)?.name ?? transaction.category_id}</p><p>Event {transaction.event_at}</p></div><form className="inline-form" onSubmit={(event) => { event.preventDefault(); correctionMutation.mutate(); }}><label>Replacement amount<input value={correctionAmount} onChange={(event) => setCorrectionAmount(event.target.value)} required /></label><button type="submit" disabled={correctionMutation.isPending}>{correctionMutation.isPending ? "Saving…" : "Save correction"}</button><button type="button" onClick={() => setSelectedId(null)}>Close</button></form><div><strong>Correction history</strong>{corrections.isPending && <p>Loading correction history…</p>}{corrections.data?.map((correction) => <p key={correction.id}>#{correction.correction_sequence}: {String(correction.before_snapshot.amount)} → {String(correction.after_snapshot.amount)}</p>)}</div></>}</article>)}</div>
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

function LedgerScreen() {
  const { planId } = useParams<{ planId: string }>();
  const accounts = useQuery({ queryKey: ["plans", planId, "accounts"], queryFn: () => getAccounts(planId ?? ""), enabled: Boolean(planId) });
  const categories = useQuery({ queryKey: ["plans", planId, "categories"], queryFn: () => getCategories(planId ?? ""), enabled: Boolean(planId) });
  if (!planId) return <Navigate to="/plans" replace />;
  return <main className="page"><header className="page-header"><Link to={`/plans/${planId}/accounts`}>← Accounts</Link><p className="eyebrow">Ledger core</p><h1>Ledger</h1><p>Exact, Plan-scoped activity and monthly envelopes.</p></header><TaxonomyPanel planId={planId} /><TransactionPanel planId={planId} accounts={accounts.data ?? []} categories={categories.data ?? []} /><BudgetPanel planId={planId} categories={categories.data ?? []} /></main>;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/plans" element={<PlanScreen />} />
      <Route path="/plans/:planId/accounts" element={<AccountsScreen />} />
      <Route path="/plans/:planId/ledger" element={<LedgerScreen />} />
      <Route path="*" element={<Navigate to="/plans" replace />} />
    </Routes>
  );
}

export function App() {
  return <AppRoutes />;
}
