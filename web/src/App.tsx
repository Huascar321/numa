import { FormEvent, useState } from "react";
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
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const createMutation = useMutation({
    mutationFn: () => createPlan(newClientId(), {
      name,
      reporting_currency_code: currency,
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
    </main>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/plans" element={<PlanScreen />} />
      <Route path="/plans/:planId/accounts" element={<AccountsScreen />} />
      <Route path="*" element={<Navigate to="/plans" replace />} />
    </Routes>
  );
}

export function App() {
  return <AppRoutes />;
}
