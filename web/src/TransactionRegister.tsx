import { FormEvent, Fragment, ReactNode, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Account,
  Category,
  Tag,
  Transaction,
  correctTransaction,
  getTransactionCorrections,
  newClientId,
} from "./api";
import { RegisterIcon } from "./RegisterIcon";
import { formatMoney, formatTransactionDate, toDateTimeLocal } from "./money";

type RegisterProps = {
  planId: string;
  transactions: Transaction[];
  accounts: Account[];
  categories: Category[];
  tags: Tag[];
  accountFilter: string;
  onAccountFilterChange: (accountId: string) => void;
  entry?: ReactNode;
  onChanged: () => Promise<unknown>;
};

type KindFilter = "all" | "expense" | "income";

function categoryName(category: Category | undefined): string {
  if (!category) return "Pendientes";
  return category.name;
}

function matchesQuery(transaction: Transaction, query: string, account: string, category: string): boolean {
  if (!query) return true;
  const haystack = [
    transaction.merchant,
    transaction.memo,
    transaction.amount,
    formatMoney(transaction.amount, transaction.currency_code),
    formatTransactionDate(transaction.event_at),
    transaction.currency_code,
    account,
    category,
  ].filter(Boolean).join(" ").toLocaleLowerCase();
  return haystack.includes(query.toLocaleLowerCase());
}

export function TransactionRegister({
  planId,
  transactions,
  accounts,
  categories,
  tags,
  accountFilter,
  onAccountFilterChange,
  entry,
  onChanged,
}: RegisterProps) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<KindFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const accountMap = new Map(accounts.map((account) => [account.id, account]));
  const categoryMap = new Map(categories.map((category) => [category.id, category]));
  const visible = transactions.filter((transaction) => {
    if (accountFilter && transaction.account_id !== accountFilter) return false;
    if (kind !== "all" && transaction.type !== kind) return false;
    return matchesQuery(
      transaction,
      query,
      accountMap.get(transaction.account_id)?.name ?? "",
      categoryName(transaction.category_id ? categoryMap.get(transaction.category_id) : undefined),
    );
  });
  const selected = transactions.find((transaction) => transaction.id === selectedId) ?? null;

  return (
    <section className="register" aria-label="Transaction register">
      <div className="register-toolbar">
        <label className="register-search">
          Search
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Payee, category, memo…"
          />
        </label>
        <label>
          Account
          <select value={accountFilter} onChange={(event) => onAccountFilterChange(event.target.value)}>
            <option value="">All accounts</option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name} · {account.currency_code}
              </option>
            ))}
          </select>
        </label>
        <label>
          Type
          <select value={kind} onChange={(event) => setKind(event.target.value as KindFilter)}>
            <option value="all">All types</option>
            <option value="expense">Expenses</option>
            <option value="income">Income</option>
          </select>
        </label>
        <span className="register-count" role="status">
          {visible.length} {visible.length === 1 ? "transaction" : "transactions"}
        </span>
      </div>

      <div className="register-scroll">
        <table className="register-table">
          <caption className="sr-only">Transactions</caption>
          <thead>
            <tr>
              <th scope="col"><span className="register-column-label"><RegisterIcon name="date" />Date</span></th>
              <th scope="col"><span className="register-column-label"><RegisterIcon name="account" />Account</span></th>
              <th scope="col"><span className="register-column-label"><RegisterIcon name="payee" />Payee</span></th>
              <th scope="col"><span className="register-column-label"><RegisterIcon name="category" />Category</span></th>
              <th scope="col"><span className="register-column-label"><RegisterIcon name="memo" />Memo</span></th>
              <th scope="col" className="register-amount-column"><span className="register-column-label"><RegisterIcon name="outflow" />Outflow</span></th>
              <th scope="col" className="register-amount-column"><span className="register-column-label"><RegisterIcon name="inflow" />Inflow</span></th>
              <th scope="col"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {entry && <tr className="entry-row"><td colSpan={8}>{entry}</td></tr>}
            {visible.map((transaction) => {
              const account = accountMap.get(transaction.account_id);
              const category = transaction.category_id ? categoryMap.get(transaction.category_id) : undefined;
              const isExpense = transaction.type === "expense";
              return (
                <Fragment key={transaction.id}>
                  <tr className={selectedId === transaction.id ? "is-selected" : ""}>
                    <td data-label="Date">{formatTransactionDate(transaction.event_at)}</td>
                    <td data-label="Account">
                      <span className="register-account-dot" aria-hidden="true" data-type={account?.account_type}>
                        {account?.account_type === "Credit Card" ? "▭" : "▤"}
                      </span>
                      {account?.name ?? "Unknown account"}
                    </td>
                    <td data-label="Payee">{transaction.merchant || "—"}</td>
                    <td data-label="Category">{categoryName(category)}</td>
                    <td data-label="Memo">{transaction.memo || "—"}</td>
                    <td data-label="Outflow" className="register-amount outflow">
                      {isExpense ? formatMoney(transaction.amount, transaction.currency_code) : ""}
                    </td>
                    <td data-label="Inflow" className="register-amount inflow">
                      {isExpense ? "" : formatMoney(transaction.amount, transaction.currency_code)}
                    </td>
                    <td className="register-actions">
                      <button
                        type="button"
                        aria-label={`Edit ${transaction.merchant || (isExpense ? "expense" : "income")} transaction`}
                        aria-expanded={selectedId === transaction.id}
                        onClick={() => setSelectedId(selectedId === transaction.id ? null : transaction.id)}
                      >
                        <RegisterIcon name="edit" /> Edit
                      </button>
                    </td>
                  </tr>
                  {selectedId === transaction.id && selected && (
                    <tr className="register-editor-row">
                      <td colSpan={8}>
                        <CorrectionEditor
                          planId={planId}
                          transaction={selected}
                          accounts={accounts}
                          categories={categories}
                          tags={tags}
                          onClose={() => setSelectedId(null)}
                          onSaved={onChanged}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      {visible.length === 0 && (
        <p className="empty-state">
          {transactions.length === 0
            ? "No manual transactions yet."
            : "No transactions match this view."}
        </p>
      )}
    </section>
  );
}

function CorrectionEditor({ planId, transaction, accounts, categories, tags, onClose, onSaved }: {
  planId: string;
  transaction: Transaction;
  accounts: Account[];
  categories: Category[];
  tags: Tag[];
  onClose: () => void;
  onSaved: () => Promise<unknown>;
}) {
  const [amount, setAmount] = useState(transaction.amount);
  const [accountId, setAccountId] = useState(transaction.account_id);
  const [categoryId, setCategoryId] = useState(transaction.category_id ?? "");
  const [eventAt, setEventAt] = useState(toDateTimeLocal(transaction.event_at));
  const [merchant, setMerchant] = useState(transaction.merchant ?? "");
  const [memo, setMemo] = useState(transaction.memo ?? "");
  const [selectedTags, setSelectedTags] = useState<string[]>(transaction.tags);
  const sameCurrencyAccounts = accounts.filter(
    (account) => account.currency_code === transaction.currency_code
      && (account.status === "active" || account.id === transaction.account_id),
  );
  const correctionCategories = categories.filter(
    (category) => category.id === transaction.category_id
      || (category.status === "active" && !category.payment_account_id),
  );
  const corrections = useQuery({
    queryKey: ["plans", planId, "transactions", transaction.id, "corrections"],
    queryFn: () => getTransactionCorrections(planId, transaction.id),
  });
  const mutation = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = {};
      if (amount !== transaction.amount) payload.amount = amount;
      if (accountId !== transaction.account_id) payload.account_id = accountId;
      if ((categoryId || null) !== (transaction.category_id ?? null)) payload.category_id = categoryId || null;
      if (new Date(eventAt).toISOString() !== new Date(transaction.event_at).toISOString()) {
        payload.event_at = new Date(eventAt).toISOString();
      }
      if ((merchant || null) !== transaction.merchant) payload.merchant = merchant || null;
      if ((memo || null) !== transaction.memo) payload.memo = memo || null;
      if ([...selectedTags].sort().join("|") !== [...(transaction.tags ?? [])].sort().join("|")) {
        payload.tags = selectedTags;
      }
      if (Object.keys(payload).length === 0) {
        throw new Error("Change at least one field before saving a correction.");
      }
      return correctTransaction(planId, transaction.id, newClientId(), payload);
    },
    onSuccess: async () => {
      await onSaved();
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <form className="register-editor" onSubmit={submit}>
      <div className="register-editor-heading">
        <div>
          <p className="eyebrow">Immutable correction</p>
          <strong>{transaction.type === "expense" ? "Expense" : "Income"} correction</strong>
        </div>
        <button type="button" onClick={onClose} aria-label="Close correction">×</button>
      </div>
      <div className="register-editor-grid">
        <label>Replacement amount<input inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} required /></label>
        <label>Correction account<select value={accountId} onChange={(event) => setAccountId(event.target.value)}>
          {sameCurrencyAccounts.map((account) => <option key={account.id} value={account.id}>{account.name} · {account.currency_code}</option>)}
        </select></label>
        <label>Correction category<select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
          <option value="">Pendientes</option>
          {correctionCategories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
        </select></label>
        <label>Correction date and time<input type="datetime-local" value={eventAt} onChange={(event) => setEventAt(event.target.value)} required /></label>
        <label>Correction merchant<input value={merchant} onChange={(event) => setMerchant(event.target.value)} /></label>
        <label>Correction memo<input value={memo} onChange={(event) => setMemo(event.target.value)} /></label>
      </div>
      <fieldset className="tag-fieldset register-editor-tags">
        <legend>Correction tags</legend>
        {tags.filter((tag) => tag.status === "active").map((tag) => (
          <label key={tag.id}>
            <input
              type="checkbox"
              checked={selectedTags.includes(tag.id)}
              onChange={(event) => setSelectedTags((current) => event.target.checked
                ? [...current, tag.id]
                : current.filter((id) => id !== tag.id))}
            />
            {tag.name}
          </label>
        ))}
      </fieldset>
      <div className="card-actions">
        <button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Saving…" : "Save correction"}</button>
        <button type="button" onClick={onClose}>Cancel</button>
      </div>
      {mutation.isError && <p role="alert">{mutation.error instanceof Error ? mutation.error.message : "The correction failed."}</p>}
      {mutation.isSuccess && <p role="status" className="completion-note">Correction saved. The original entry remains in the audit history.</p>}
      <div className="register-history">
        <strong>Correction history</strong>
        {corrections.isPending && <p>Loading correction history…</p>}
        {corrections.data?.map((correction) => (
          <p key={correction.id}>
            #{correction.correction_sequence}: {String(correction.before_snapshot.amount)} → {String(correction.after_snapshot.amount)}
          </p>
        ))}
      </div>
    </form>
  );
}
