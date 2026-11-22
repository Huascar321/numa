import { FormEvent, useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Account,
  Category,
  CategoryGroup,
  TransactionCreatePayload,
  createTransaction,
  getCategories,
  getCategoryGroups,
  getTags,
  getTransactions,
  newClientId,
} from "./api";
import { toDateTimeLocal } from "./money";
import { RegisterIcon } from "./RegisterIcon";
import "./entry.css";

const phoneQuery = "(max-width: 1000px)";
function subscribePhone(update: () => void) {
  const media = window.matchMedia?.(phoneQuery);
  media?.addEventListener("change", update);
  return () => media?.removeEventListener("change", update);
}
const isPhone = () => window.matchMedia?.(phoneQuery).matches ?? false;
const localNow = () => toDateTimeLocal(new Date().toISOString());
const normalize = (name: string) => name.trim().toLowerCase();

function CategoryPicker({
  categories,
  groups,
  recentIds,
  value,
  onChange,
}: {
  categories: Category[];
  groups: CategoryGroup[];
  recentIds?: string[];
  value: string;
  onChange: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const toggle = useRef<HTMLButtonElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const resultId = useId();
  const selected = categories.find((c) => c.id === value);
  const rows = new Map<string, Category[]>();
  const groupNames = new Map(groups.map((group) => [group.id, group.name]));
  for (const category of categories) {
    const groupName = groupNames.get(category.group_id ?? "") ?? "Other categories";
    if (!normalize(groupName + " " + category.name).includes(normalize(filter))) continue;
    const list = rows.get(groupName) ?? [];
    list.push(category);
    rows.set(groupName, list);
  }
  const recentOptions = (recentIds ?? []).filter((id) => id !== value).slice(0, 5);
  useEffect(() => {
    if (open) search.current?.focus();
  }, [open]);
  function close() {
    setOpen(false);
    setFilter("");
    toggle.current?.focus();
  }
  function select(id: string) {
    onChange(id);
    close();
  }
  return (
    <div
      className="entry-category"
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) {
          setOpen(false);
          setFilter("");
        }
      }}
      onKeyDown={(e) => {
        if (open && e.key === "Escape") {
          e.preventDefault();
          e.stopPropagation();
          close();
        }
      }}
    >
      <span className="entry-label">Category</span>
      <button
        type="button"
        ref={toggle}
        className="category-toggle"
        aria-label={`Category: ${selected?.name ?? "Pendientes"}`}
        aria-expanded={open}
        aria-controls={resultId}
        onClick={() => {
          setFilter("");
          setOpen(!open);
        }}
      >
        <span>{selected?.name ?? "Pendientes"}</span>
        <span aria-hidden="true">⌄</span>
      </button>
      {open && (
        <div className="category-menu" id={resultId}>
          <input
            ref={search}
            aria-label="Search categories"
            placeholder="Search categories…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === "ArrowDown") {
                e.preventDefault();
                const first = e.currentTarget.parentElement?.querySelector<HTMLButtonElement>("button");
                if (e.key === "ArrowDown") first?.focus();
                else first?.click();
              }
            }}
          />
          <div className="category-options">
            {!filter && recentOptions.length > 0 && (
              <div role="group" aria-label="Recent categories for this payee">
                <strong>Recent for this payee</strong>
                {recentOptions.map((id) => (
                  <button type="button" key={id} onClick={() => select(id)}>
                    {categories.find((c) => c.id === id)?.name}
                  </button>
                ))}
              </div>
            )}
            {Array.from(rows, ([name, items]) => (
              <div key={name} role="group" aria-label={name}>
                <strong>{name}</strong>
                {items.map((c) => (
                  <button
                    type="button"
                    key={c.id}
                    aria-pressed={c.id === value || (!value && c.is_pending)}
                    onClick={() => select(c.is_pending ? "" : c.id)}
                  >
                    {c.name}
                  </button>
                ))}
              </div>
            ))}
            {!rows.size && <p role="status">No matching categories.</p>}
          </div>
        </div>
      )}
    </div>
  );
}

type EntryProps = {
  planId: string;
  accounts: Account[];
  accountId?: string;
  categoryId?: string;
  inRegister?: boolean;
  onClose: () => void;
  onSaved: () => void;
};

export function ExpenseEntry({
  planId,
  accounts,
  accountId,
  categoryId,
  inRegister,
  onClose,
  onSaved,
}: EntryProps) {
  const phone = useSyncExternalStore(subscribePhone, isPhone, () => false);
  const modal = !inRegister || phone;
  const dialog = useRef<HTMLDialogElement>(null);
  const form = useRef<HTMLFormElement>(null);
  const focusEntry = () => form.current?.querySelector<HTMLInputElement>("[data-first]")?.focus();
  useEffect(() => {
    const parentDialog = dialog.current;
    if (modal && parentDialog && !parentDialog.open) parentDialog.showModal();
    focusEntry();
    return () => {
      if (parentDialog?.open) parentDialog.close();
    };
  }, [modal]);

  const cache = useQueryClient();
  const categoriesQuery = useQuery({
    queryKey: ["plans", planId, "categories"],
    queryFn: () => getCategories(planId),
  });
  const groups = useQuery({
    queryKey: ["plans", planId, "category-groups"],
    queryFn: () => getCategoryGroups(planId),
  });
  const history = useQuery({
    queryKey: ["plans", planId, "transactions"],
    queryFn: () => getTransactions(planId),
  });
  const tags = useQuery({ queryKey: ["plans", planId, "tags"], queryFn: () => getTags(planId) });
  const categories = useMemo(
    () => (categoriesQuery.data ?? []).filter((c) => c.status === "active" && !c.payment_account_id),
    [categoriesQuery.data],
  );
  const activeAccounts = accounts.filter((a) => a.status === "active");
  const [chosenAccount, setAccount] = useState(accountId ?? "");
  const account =
    activeAccounts.find((a) => a.id === chosenAccount) ??
    (!chosenAccount && activeAccounts.length === 1 ? activeAccounts[0] : undefined);
  const [type, setType] = useState<"expense" | "income">("expense");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(localNow);
  const [payee, setPayee] = useState("");
  const [chosenCategory, setCategory] = useState<string | undefined>(categoryId);
  const [memo, setMemo] = useState("");
  const [photo, setPhoto] = useState("");
  const [location, setLocation] = useState("");
  const [metadata, setMetadata] = useState("");
  const [provenance, setProvenance] = useState("");
  const [tagIds, setTags] = useState<string[]>([]);
  const [savedAnother, setSavedAnother] = useState(false);
  const payeeList = useId();

  const recent = useMemo(() => {
    const result = new Map<string, { name: string; category: string; recentIds: string[] }>();
    const eligible = new Set(categories.filter((c) => !c.is_pending).map((c) => c.id));
    // The ledger serves effective (corrected) transactions, newest event first.
    for (const tx of history.data ?? []) {
      if ("legs" in tx || tx.type !== type || !tx.merchant?.trim()) continue;
      const key = normalize(tx.merchant);
      const id = tx.category_id && eligible.has(tx.category_id) ? tx.category_id : "";
      const previous = result.get(key);
      if (!previous) result.set(key, { name: tx.merchant, category: id, recentIds: id ? [id] : [] });
      else if (id && previous.recentIds.length < 6 && !previous.recentIds.includes(id))
        previous.recentIds.push(id);
    }
    return result;
  }, [history.data, categories, type]);
  const payeeHistory = recent.get(normalize(payee));
  const suggested = payeeHistory?.category;
  const category = chosenCategory ?? suggested ?? "";
  const identity = useRef<string | null>(null);
  const saving = useRef(false);

  const save = useMutation({
    mutationFn: async (another: boolean) => {
      if (!account) throw new Error("Choose an active account.");
      if (!/^\d+(?:[.,]\d+)?$/.test(amount.trim()) || !/[1-9]/.test(amount))
        throw new Error("Enter an amount greater than zero.");
      const payload: TransactionCreatePayload = {
        type,
        account_id: account.id,
        currency_code: account.currency_code,
        amount: amount.trim().replace(",", "."),
        event_at: new Date(date).toISOString(),
        category_id: category || undefined,
        merchant: payee.trim() || undefined,
        memo: memo || undefined,
        tags: tagIds,
        photo_reference: photo || undefined,
        location: parseOptionalJson(location, "Location"),
        source_metadata: parseOptionalJson(metadata, "Source metadata"),
        provenance: parseOptionalJson(provenance, "Provenance"),
      };
      // The same draft must keep its identity even if a response gets lost.
      identity.current ??= newClientId();
      await createTransaction(planId, identity.current, payload);
      return another;
    },
    onSuccess: async (another) => {
      identity.current = null;
      await Promise.all(
        ["transactions", "accounts", "budget"].map((key) =>
          cache.invalidateQueries({ queryKey: ["plans", planId, key] }),
        ),
      );
      onSaved();
      if (!another) {
        onClose();
        return;
      }
      setPayee("");
      setAmount("");
      setMemo("");
      setCategory(categoryId);
      setDate(localNow());
      setPhoto("");
      setLocation("");
      setMetadata("");
      setProvenance("");
      setTags([]);
      setSavedAnother(true);
      requestAnimationFrame(focusEntry);
    },
    onSettled: () => {
      saving.current = false;
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    if (saving.current) return;
    saving.current = true;
    setSavedAnother(false);
    save.mutate(
      ((event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null)?.value === "another",
    );
  }
  const dateField = (
    <label className="entry-date">
      Date and time
      <input
        type="datetime-local"
        required
        data-first={!modal || undefined}
        value={date}
        onChange={(e) => setDate(e.target.value)}
      />
    </label>
  );
  const accountField = (
    <label className="entry-account">
      Account
      <select
        required
        aria-label="Transaction account"
        value={account?.id ?? ""}
        onChange={(e) => setAccount(e.target.value)}
      >
        {!account && <option value="">Choose account</option>}
        {activeAccounts.map((a) => (
          <option key={a.id} value={a.id}>
            {a.name} · {a.currency_code}
          </option>
        ))}
      </select>
    </label>
  );
  const payeeField = (
    <label className="entry-payee">
      Payee
      <input
        list={payeeList}
        value={payee}
        autoComplete="off"
        placeholder={type === "expense" ? "Who did you pay?" : "Who paid you?"}
        onChange={(e) => setPayee(e.target.value)}
      />
      <datalist id={payeeList}>
        {Array.from(recent, ([key, item]) => (
          <option key={key} value={item.name} />
        ))}
      </datalist>
    </label>
  );
  const categoryField = (
    <div className="entry-category-cell">
      <CategoryPicker
        categories={categories}
        groups={groups.data ?? []}
        recentIds={payeeHistory?.recentIds}
        value={category}
        onChange={setCategory}
      />
      {chosenCategory === undefined && suggested && <small>From this payee’s last transaction</small>}
    </div>
  );
  const memoField = (
    <label className="entry-memo">
      Memo
      <input value={memo} placeholder="Optional" onChange={(e) => setMemo(e.target.value)} />
    </label>
  );

  const content = (
    <form
      ref={form}
      aria-label="Transaction entry"
      className={`expense-entry ${modal ? "entry-modal" : "entry-inline"}`}
      onSubmit={submit}
      onKeyDown={(event) => {
        if (!modal && event.key === "Escape" && !event.defaultPrevented && !saving.current) {
          event.preventDefault();
          onClose();
        }
      }}
    >
      <fieldset disabled={save.isPending}>
        {modal && (
          <header className="entry-header">
            <h2>Add transaction</h2>
            <button type="button" aria-label="Cancel transaction" onClick={onClose}>
              ×
            </button>
          </header>
        )}
        <div className="entry-fields">
          {modal ? (
            <>
              <div className="entry-type" role="group" aria-label="Transaction type">
                {(["expense", "income"] as const).map((kind) => (
                  <button type="button" key={kind} aria-pressed={type === kind} onClick={() => setType(kind)}>
                    <RegisterIcon name={kind === "expense" ? "outflow" : "inflow"} />{" "}
                    {kind === "expense" ? "Expense" : "Income"}
                  </button>
                ))}
              </div>
              <label className="entry-amount">
                Amount <span>{account?.currency_code}</span>
                <input
                  data-first
                  required
                  inputMode="decimal"
                  aria-label="Amount"
                  value={amount}
                  placeholder="0.00"
                  onChange={(e) => setAmount(e.target.value)}
                />
              </label>
              {payeeField}
              {categoryField}
              {accountField}
              {dateField}
              {memoField}
            </>
          ) : (
            <>
              {dateField}
              {accountField}
              {payeeField}
              {categoryField}
              {memoField}
              {(["expense", "income"] as const).map((kind) => (
                <label key={kind}>
                  {kind === "expense" ? "Outflow" : "Inflow"}
                  <input
                    inputMode="decimal"
                    value={type === kind ? amount : ""}
                    placeholder="0.00"
                    onChange={(e) => {
                      setType(kind);
                      setAmount(e.target.value);
                    }}
                  />
                </label>
              ))}
            </>
          )}
        </div>
        <details className="entry-evidence">
          <summary>Additional evidence</summary>
          <div className="form-grid">
            <label>
              Photo reference (opaque)
              <input value={photo} onChange={(e) => setPhoto(e.target.value)} />
            </label>
            <label>
              Location JSON
              <input value={location} onChange={(e) => setLocation(e.target.value)} />
            </label>
            <label>
              Source metadata JSON
              <input value={metadata} onChange={(e) => setMetadata(e.target.value)} />
            </label>
            <label>
              Provenance JSON
              <input value={provenance} onChange={(e) => setProvenance(e.target.value)} />
            </label>
          </div>
          {tags.data?.some((t) => t.status === "active") && (
            <fieldset className="tag-fieldset">
              <legend>Tags</legend>
              {tags.data
                .filter((t) => t.status === "active")
                .map((t) => (
                  <label key={t.id}>
                    <input
                      type="checkbox"
                      checked={tagIds.includes(t.id)}
                      onChange={(e) =>
                        setTags(e.target.checked ? [...tagIds, t.id] : tagIds.filter((id) => id !== t.id))
                      }
                    />
                    {t.name}
                  </label>
                ))}
            </fieldset>
          )}
        </details>
        {!activeAccounts.length && <p role="status">Add an active account to record transactions.</p>}
        {categoriesQuery.isError && (
          <p role="alert">
            Categories could not be loaded.{" "}
            <button type="button" onClick={() => void categoriesQuery.refetch()}>
              Retry
            </button>
          </p>
        )}
        {save.isError && (
          <p role="alert" className="error">
            {save.error.message}
          </p>
        )}
        {savedAnother && (
          <p role="status" className="completion-note">
            Transaction saved.
          </p>
        )}
        <footer className="entry-actions">
          {!modal && (
            <button type="button" onClick={onClose}>
              Cancel
            </button>
          )}
          <button type="submit" disabled={!account || !categoriesQuery.isSuccess}>
            <RegisterIcon name="save" /> {save.isPending ? "Saving…" : "Save"}
          </button>
          <button
            type="submit"
            value="another"
            className="entry-another"
            disabled={!account || !categoriesQuery.isSuccess}
          >
            <RegisterIcon name="another" /> Save and add another
          </button>
        </footer>
      </fieldset>
    </form>
  );
  return modal
    ? createPortal(
        <dialog
          ref={dialog}
          className="entry-dialog"
          aria-label="Add transaction"
          onCancel={(e) => {
            e.preventDefault();
            if (!saving.current) onClose();
          }}
        >
          {content}
        </dialog>,
        document.body,
      )
    : content;
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
