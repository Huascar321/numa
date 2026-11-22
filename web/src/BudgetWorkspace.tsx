import { FormEvent, Fragment, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Link, useOutletContext, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Account, BudgetActionInput, Category, CategoryEnvelope, CategoryGroup, GoalInput,
  MonthlySummary, Plan, budgetAction, createCategory, createCategoryGroup, getAccounts,
  getCategories, getCategoryGroups, getMonthlySummary, getPlan, newClientId, updateGoal } from "./api";
import { ExpenseEntry } from "./ExpenseEntry";
import { WorkspaceFrame } from "./WorkspaceLayout";
import { formatMoney } from "./money";
import "./budget.css";

// Display classification only. All monetary arithmetic belongs to the server.
export const moneyState = (value = "0") => /^-0*(?:\.0*)?$/.test(value) || /^0*(?:\.0*)?$/.test(value)
  ? "zero" : value.startsWith("-") ? "negative" : "positive";
const message = (error: unknown) => error instanceof Error ? error.message : "The request failed. Please retry.";

function localMonth(timezone = "America/La_Paz") {
  const parts = new Intl.DateTimeFormat("en", { timeZone: timezone, year: "numeric", month: "2-digit" }).formatToParts(new Date());
  return `${parts.find(p => p.type === "year")?.value}-${parts.find(p => p.type === "month")?.value}`;
}

function shiftedMonth(month: string, delta: number) {
  const [year, number] = month.split("-").map(Number);
  const next = new Date(Date.UTC(year, number - 1 + delta, 1));
  return next.toISOString().slice(0, 7);
}

export function BudgetScreen() {
  const { planId = "" } = useParams();
  const embedded = Boolean(useOutletContext<{workspace:boolean} | undefined>()?.workspace);
  const plan = useQuery({ queryKey: ["plans", planId], queryFn: () => getPlan(planId) });
  const accounts = useQuery({ queryKey: ["plans", planId, "accounts"], queryFn: () => getAccounts(planId) });
  const categories = useQuery({ queryKey: ["plans", planId, "categories"], queryFn: () => getCategories(planId) });
  const groups = useQuery({ queryKey: ["plans", planId, "category-groups"], queryFn: () => getCategoryGroups(planId) });
  if ([plan, accounts, categories, groups].some(q => q.isError)) return <main className="workspace-page"><p role="alert">The budget workspace could not be loaded.</p><button onClick={() => {
    void plan.refetch(); void accounts.refetch(); void categories.refetch(); void groups.refetch();
  }}>Retry workspace</button><p><Link to="/plans">Back to Plans</Link></p></main>;
  if (!plan.data || !accounts.data || !categories.data || !groups.data) return <main className="workspace-page"><p role="status">Loading your budget…</p></main>;
  return <BudgetWorkspace embedded={embedded} key={planId} plan={plan.data} accounts={accounts.data} categories={categories.data} groups={groups.data} />;
}

type WorkspaceProps = { plan: Plan; accounts: Account[]; categories: Category[]; groups: CategoryGroup[]; embedded?:boolean };
type Filter = "all" | "underfunded" | "overspent" | "available";

const subscribeCompact = (notify:()=>void) => {
  const media = window.matchMedia?.("(max-width: 1100px)");
  media?.addEventListener("change", notify);
  return () => media?.removeEventListener("change", notify);
};
const isCompact = () => window.matchMedia?.("(max-width: 1100px)").matches ?? false;

export function BudgetWorkspace({ plan, accounts, categories, groups, embedded=false }: WorkspaceProps) {
  const cache = useQueryClient();
  const [month, setMonth] = useState(() => localMonth(plan.budget_timezone));
  const [entryCategory, setEntryCategory] = useState<string | null>(null);
  const [entryNotice, setEntryNotice] = useState("");
  function openEntry(category = "") { setEntryNotice(""); setEntryCategory(category); }
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
  const command = useRef<{ signature: string; id: string } | null>(null);
  const summary = useQuery({ queryKey: ["plans", plan.id, "budget", month], queryFn: () => getMonthlySummary(plan.id, month) });
  const refresh = () => cache.invalidateQueries({ queryKey: ["plans", plan.id] });
  const mutation = useMutation({ mutationFn: (payload: BudgetActionInput) => {
    const signature = JSON.stringify(payload);
    if (command.current?.signature !== signature) command.current = { signature, id: newClientId() };
    return budgetAction(plan.id, command.current.id, payload);
  }, onSuccess: async () => { command.current = null; await refresh(); } });
  const [notice, setNotice] = useState("");
  const compact = useSyncExternalStore(subscribeCompact, isCompact, () => false);
  const sheet = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (compact && selectedId && sheet.current && !sheet.current.open) sheet.current.showModal();
  }, [compact, selectedId]);
  const submit = (payload: BudgetActionInput) => { setNotice(""); mutation.mutate(payload, { onSuccess: () => setNotice("Budget updated.") }); };
  const categoryMap = new Map(categories.map(c => [c.id, c]));
  const accountMap = new Map(accounts.map(a => [a.id, a]));
  const nameOf = (c?: Category) => c?.payment_account_id ? accountMap.get(c.payment_account_id)?.name ?? "Card payment" : c?.name ?? "Category";
  const selected = summary.data?.categories.find(e => e.category_id === selectedId);
  const selectedCategory = selected ? categoryMap.get(selected.category_id) : undefined;
  const visible = (summary.data?.categories ?? []).filter(e => {
    const category = categoryMap.get(e.category_id);
    if (category?.status === "archived" && moneyState(e.available) === "zero" && moneyState(e.activity) === "zero") return false;
    if (filter === "underfunded") return e.goal?.status === "underfunded" || moneyState(e.payment_shortfall) === "positive";
    if (filter === "overspent") return moneyState(e.available) === "negative";
    if (filter === "available") return moneyState(e.available) === "positive";
    return true;
  });
  const groupRows = new Map<string, CategoryEnvelope[]>();
  for (const e of visible) {
    const c = categoryMap.get(e.category_id);
    const key = c?.payment_account_id ? "payments" : c?.group_id ?? "ungrouped";
    groupRows.set(key, [...(groupRows.get(key) ?? []), e]);
  }
  const groupOrder = ["payments", ...groups.map(g => g.id), "ungrouped"].filter(key => groupRows.has(key));
  const changeMonth = (value: string) => { if (/^\d{4}-(0[1-9]|1[0-2])$/.test(value) && !value.startsWith("0000")) { setMonth(value); setNotice(""); mutation.reset(); } };
  const inspector = selected && selectedCategory && summary.data ? <CategoryInspector key={`${selectedId}:${month}`} category={selectedCategory} envelope={selected}
    name={nameOf(selectedCategory)} summary={summary.data} categories={categories} nameOf={nameOf} planId={plan.id}
    onAddExpense={() => openEntry(selectedCategory.id)} onClose={() => setSelectedId(null)} onAction={submit} pending={mutation.isPending} onSaved={refresh}
    error={mutation.isError ? message(mutation.error) : undefined} notice={notice} /> : null;
  const content = <><main className="budget-screen">
      <header className="budget-header">
        <div className="budget-month-control"><button aria-label="Previous month" disabled={mutation.isPending || month === "0001-01"} onClick={() => changeMonth(shiftedMonth(month, -1))}>←</button>
          <div><p className="eyebrow">Monthly budget</p><h1>{new Intl.DateTimeFormat("en", {month:"long",year:"numeric",timeZone:"UTC"}).format(new Date(`${month}-01T12:00:00Z`))}</h1>
          <label className="budget-month-label">Choose month<input type="month" value={month} disabled={mutation.isPending} onChange={e => changeMonth(e.target.value)} /></label></div>
          <button aria-label="Next month" disabled={mutation.isPending || month === "9999-12"} onClick={() => changeMonth(shiftedMonth(month, 1))}>→</button>
        </div>
        {summary.data && <div className={`ready-card ${moneyState(summary.data.ready_to_assign)}`} aria-label="Ready to Assign">
          <small>Ready to Assign</small>
          <strong>{formatMoney(summary.data.ready_to_assign, summary.data.currency)}</strong>
          <span>{moneyState(summary.data.ready_to_assign) === "negative" ? "Overassigned — move money back" : moneyState(summary.data.ready_to_assign) === "zero" ? "All money assigned" : "Money waiting for a job"}</span>
        </div>}
      </header>
      <nav className="budget-filters" aria-label="Budget filters">{([['all','All categories'],['underfunded','Underfunded'],['overspent','Overspent'],['available','Money available']] as const).map(([value,label]) =>
        <button key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}
        <div className="entry-launcher"><button className="budget-entry-button" onClick={() => openEntry()}>+ Add transaction</button></div>
      </nav>
      {entryNotice && <p role="status" className="budget-feedback">{entryNotice}</p>}
      {!selected && mutation.isError && <p role="alert" className="budget-feedback error">{message(mutation.error)}</p>}
      {!selected && notice && <p role="status" className="budget-feedback">{notice}</p>}
      {summary.isError && <div className="budget-feedback"><p role="alert">This month could not be loaded.</p><button onClick={() => void summary.refetch()}>Retry month</button></div>}
      {summary.isPending && <p role="status" className="budget-feedback">Loading monthly budget…</p>}
      <div className="budget-body">
        <section className="budget-categories" aria-label="Budget categories">
          <CategoryComposer planId={plan.id} groups={groups} onSaved={refresh} />
          {summary.data && <>
            <table className="budget-table"><thead><tr><th scope="col">Category</th><th scope="col">Assigned</th><th scope="col">Activity</th><th scope="col">Available</th></tr></thead>
              <tbody>{groupOrder.map(key => <Fragment key={key}>
                <tr className="budget-group"><th colSpan={4}><button aria-expanded={!collapsed.has(key)} onClick={() => setCollapsed(previous => {
                  const next = new Set(previous); if (next.has(key)) next.delete(key); else next.add(key); return next;
                })}><span aria-hidden="true">{collapsed.has(key) ? "▸" : "▾"}</span> {key === "payments" ? "Credit card payments" : key === "ungrouped" ? "Other categories" : groups.find(g => g.id === key)?.name}</button></th></tr>
                {!collapsed.has(key) && groupRows.get(key)?.map(e => {
                  const c = categoryMap.get(e.category_id);
                  const name = nameOf(c);
                  const paymentNeeded = Boolean(e.payment_account_id) && moneyState(e.payment_shortfall ?? "0") === "positive";
                  const goalComplete = e.goal?.status === "completed" || e.goal?.status === "funded";
                  const statusDescription = [
                    c?.payment_account_id ? "credit card payment" : "",
                    paymentNeeded ? "payment due" : "",
                    e.goal ? `target ${e.goal.status.replaceAll("_", " ")}` : "",
                    moneyState(e.available) === "negative" ? "overspent" : "",
                  ].filter(Boolean).join(", ");
                  return <tr key={e.category_id} className={`budget-category-row ${selectedId === e.category_id ? "is-selected" : ""}`} data-status={e.goal?.status ?? (paymentNeeded ? "underfunded" : "")}>
                    <th scope="row"><button className="budget-category-name" aria-label={`View ${name} details`} aria-describedby={statusDescription ? `category-status-${e.category_id}` : undefined} aria-pressed={selectedId === e.category_id} onClick={() => { setSelectedId(e.category_id); setNotice(""); mutation.reset(); }}>
                      <span className="budget-category-title">
                        <span>{name}</span>
                        {c?.payment_account_id && <span className="budget-badge budget-badge-payment">Payment</span>}
                        {paymentNeeded && <span className="budget-badge budget-badge-alert">Due</span>}
                        {e.goal?.status === "underfunded" && !paymentNeeded && <span className="budget-badge budget-badge-alert">Underfunded</span>}
                        {e.goal?.status === "on_track" && <span className="budget-badge budget-badge-goal">On track</span>}
                        {moneyState(e.available) === "negative" && <span className="budget-badge budget-badge-alert">Overspent</span>}
                        {c?.status === "archived" && <span className="budget-badge budget-badge-archived">Archived</span>}
                        {goalComplete && <span className={`budget-goal-mark ${e.goal?.status}`} title="Target funded" aria-hidden="true">✓</span>}
                      </span>
                      {e.goal && <span className={`budget-progress ${e.goal.status}`} aria-hidden="true"><span style={{ width: `${e.goal.progress}%` }} /></span>}
                    </button>{statusDescription && <span id={`category-status-${e.category_id}`} className="sr-only">{statusDescription}</span>}</th>
                    <td data-label="Assigned"><button className="budget-number" aria-label={`Assign money to ${name}`} onClick={() => setSelectedId(e.category_id)}>{formatMoney(e.assigned, e.currency)}</button></td>
                    <td data-label="Activity"><span className="budget-number">{formatMoney(e.activity, e.currency)}</span></td>
                    <td data-label="Available"><button className={`budget-available ${moneyState(e.available)} ${e.goal?.status === "underfunded" ? "underfunded" : ""}`} aria-label={`${name} available ${formatMoney(e.available, e.currency)}`} onClick={() => setSelectedId(e.category_id)}>{formatMoney(e.available, e.currency)}</button></td>
                  </tr>;
                })}
              </Fragment>)}</tbody>
            </table>
            {visible.length === 0 && <p className="budget-feedback">No categories match this view.</p>}
          </>}
        </section>
        <aside className="budget-inspector" aria-label="Budget details">
          {!compact && inspector ? inspector : summary.data && <MonthDetails summary={summary.data} />}
        </aside>
      </div>
    </main>
    {compact && inspector && <dialog ref={sheet} className="budget-sheet" aria-label="Category details" onCancel={() => setSelectedId(null)} onClose={() => setSelectedId(null)}>{inspector}</dialog>}
    {entryCategory !== null && <ExpenseEntry planId={plan.id} accounts={accounts} categoryId={entryCategory || undefined}
      onClose={() => setEntryCategory(null)} onSaved={() => entryCategory ? setNotice("Transaction saved.") : setEntryNotice("Transaction saved.")} />}
  </>;
  return embedded ? content : <WorkspaceFrame plan={plan} accounts={accounts}>{content}</WorkspaceFrame>;
}

function MonthDetails({summary}: {summary:MonthlySummary}) {
  return <><section className="budget-detail-card"><p className="eyebrow">The month at a glance</p><h2>Your money, assigned.</h2>
    <dl><div><dt>Assigned this month</dt><dd>{formatMoney(summary.assigned_total, summary.currency)}</dd></div><div><dt>Spending activity</dt><dd>{formatMoney(summary.activity_total, summary.currency)}</dd></div>
    <div><dt>Available in categories</dt><dd>{formatMoney(summary.available_total, summary.currency)}</dd></div><div><dt>Assigned in future months</dt><dd>{formatMoney(summary.assigned_in_future ?? "0", summary.currency)}</dd></div></dl>
    {moneyState(summary.credit_cash_inflow)!=="zero" && <p>New spendable money from cards: {formatMoney(summary.credit_cash_inflow ?? "0", summary.currency)}.</p>}
    <small>All figures in {summary.currency}. Category balances include money left over from previous months.</small>
  </section><section className="budget-detail-card"><h2>Give your money a job</h2><p>Select a category to assign money, set a target or move funds when your priorities change.</p></section>
  {moneyState(summary.reconciliation_adjustments) !== "zero" && <p className="budget-boundary">Reconciliation adjustments: {formatMoney(summary.reconciliation_adjustments ?? "0", summary.currency)}. These adjust account balances and remain outside budget funding.</p>}
  {summary.unconverted_by_currency.map(item => <p key={item.currency} className="budget-boundary">Unconverted {item.currency}: {formatMoney(item.amount, item.currency)}. Excluded from this budget.</p>)}</>;
}

function CategoryInspector({ category, envelope, name, summary, categories, nameOf, planId, onClose, onAddExpense, onAction, pending, onSaved, error, notice }: {
  category:Category; envelope:CategoryEnvelope; name:string; summary:MonthlySummary; categories:Category[]; nameOf:(c?:Category)=>string; planId:string;
  onClose:()=>void; onAddExpense:()=>void; onAction:(p:BudgetActionInput)=>void; pending:boolean; onSaved:()=>Promise<unknown>;
  error?:string; notice:string;
}) {
  const [assigned,setAssigned] = useState(envelope.assigned);
  const [source,setSource] = useState("ready");
  const [destination,setDestination] = useState(category.id);
  const [moveAmount,setMoveAmount] = useState("");
  const [goalType,setGoalType] = useState<NonNullable<GoalInput["goal_type"]>>(category.goal_type ?? "monthly_funding");
  const [target,setTarget] = useState(category.goal_target ?? "");
  const [due,setDue] = useState(category.goal_due_month ?? summary.month);
  useEffect(() => setAssigned(envelope.assigned), [envelope.assigned]);
  useEffect(() => {
    setGoalType(category.goal_type ?? "monthly_funding");
    setTarget(category.goal_target ?? "");
    setDue(category.goal_due_month ?? summary.month);
  }, [category.goal_type, category.goal_target, category.goal_due_month, summary.month]);
  const goal = useMutation({mutationFn:(payload:GoalInput)=>updateGoal(planId,category.id,payload),onSuccess:onSaved});
  const active = category.status === "active";
  const submit = (event:FormEvent, payload:BudgetActionInput) => {event.preventDefault();onAction(payload);};
  return <>
    <div className="budget-inspector-heading"><div><p className="eyebrow">{category.payment_account_id ? "Credit card payment" : "Category details"}</p><h2>{name}</h2></div><button aria-label="Close category details" disabled={pending} onClick={onClose}>×</button></div>
    {category.status === "active" && !category.payment_account_id && <button className="category-entry-button" onClick={onAddExpense}>+ Add expense</button>}
    {error && <p role="alert" className="budget-warning">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {pending && <p role="status">Saving budget…</p>}
    <section className="budget-detail-card"><p className="eyebrow">{category.payment_account_id ? "Available for payment" : "Available to spend"}</p><strong className={`budget-detail-total ${moneyState(envelope.available)}`}>{formatMoney(envelope.available, summary.currency)}</strong>
      <dl><div><dt>Left over last month</dt><dd>{formatMoney(envelope.rollover ?? "0", summary.currency)}</dd></div><div><dt>Assigned this month</dt><dd>{formatMoney(envelope.assigned, summary.currency)}</dd></div><div><dt>{category.payment_account_id ? "Funded spending − payments" : "Activity this month"}</dt><dd>{formatMoney(envelope.activity, summary.currency)}</dd></div></dl>
      {moneyState(envelope.cash_overspending) === "positive" && <p className="budget-warning">Cash overspending: {formatMoney(envelope.cash_overspending ?? "0", summary.currency)}. Cover it now; otherwise it reduces next month's Ready to Assign.</p>}
      {moneyState(envelope.credit_card_overspending) === "positive" && <p className="budget-warning">Unfunded card spending: {formatMoney(envelope.credit_card_overspending ?? "0", summary.currency)}. Add money to this category to reserve it for payment.</p>}
      {category.payment_account_id && <p>Card debt: {formatMoney(envelope.payment_debt ?? "0", summary.currency)}. Still to fund: {formatMoney(envelope.payment_shortfall ?? "0", summary.currency)}.</p>}
      {envelope.unconverted_by_currency.map(item=><p className="budget-boundary" key={item.currency}>Unconverted {item.currency}: {formatMoney(item.amount, item.currency)}</p>)}
    </section>
    {active && <>
      <form className="budget-detail-card" onSubmit={event=>submit(event,{kind:"set_assigned",month:summary.month,category_id:category.id,amount:assigned})}>
        <h3>Assign money</h3><label>Assigned this month<input inputMode="decimal" value={assigned} onChange={e=>setAssigned(e.target.value)} required /></label>
        <p className="budget-help">Set the total assigned for this month. A new adjustment preserves the previous assignments.</p><button type="submit" disabled={pending}>Save assigned amount</button>
      </form>
      <form className="budget-detail-card" onSubmit={event=>submit(event,{kind:"move",month:summary.month,source_category_id:source==="ready"?null:source,category_id:destination==="ready"?null:destination,amount:moveAmount})}>
        <h3>Move money</h3><label>From<select value={source} onChange={e=>setSource(e.target.value)}><option value="ready">Ready to Assign</option>{categories.filter(c=>c.status==="active").map(c=><option key={c.id} value={c.id}>{nameOf(c)}</option>)}</select></label>
        <label>To<select value={destination} onChange={e=>setDestination(e.target.value)}><option value="ready">Ready to Assign</option>{categories.filter(c=>c.status==="active").map(c=><option key={c.id} value={c.id}>{nameOf(c)}</option>)}</select></label>
        <label>Amount to move<input inputMode="decimal" value={moveAmount} onChange={e=>setMoveAmount(e.target.value)} required /></label><button type="submit" disabled={pending || source===destination}>Move money</button>
      </form>
    </>}
    {active && !category.is_pending && !category.payment_account_id && <section className="budget-detail-card"><h3>Target</h3>
      {envelope.goal && <><p>{envelope.goal.status.replaceAll("_"," ")} · {formatMoney(envelope.goal.required_contribution, summary.currency)} still to assign.</p>
      <button disabled={pending || goal.isPending || moneyState(envelope.goal.required_contribution)!=="positive"} onClick={()=>onAction({kind:"fund_target",month:summary.month,category_id:category.id})}>Fund target</button></>}
      <form onSubmit={event=>{event.preventDefault();goal.mutate({goal_type:goalType,goal_target:target,goal_due_month:goalType==="due_date"?due:null});}}>
        <label>Target type<select value={goalType} onChange={e=>setGoalType(e.target.value as typeof goalType)}><option value="monthly_funding">Set aside each month</option><option value="target_balance">Reach a balance</option><option value="due_date">Save by a month</option></select></label>
        <label>Target amount<input inputMode="decimal" value={target} onChange={e=>setTarget(e.target.value)} required /></label>
        {goalType==="due_date" && <label>Due month<input type="month" value={due} onChange={e=>setDue(e.target.value)} required /></label>}
        <button type="submit" disabled={pending || goal.isPending}>Save target</button>
        {envelope.goal && <button type="button" disabled={pending || goal.isPending} onClick={()=>goal.mutate({goal_type:null,goal_target:null,goal_due_month:null})}>Remove target</button>}
      </form>{goal.isError && <p role="alert">{message(goal.error)}</p>}{goal.isSuccess && <p role="status">Target saved.</p>}
    </section>}
  </>;
}

function CategoryComposer({planId,groups,onSaved}:{planId:string;groups:CategoryGroup[];onSaved:()=>Promise<unknown>}) {
  const [name,setName]=useState(""); const [group,setGroup]=useState("");const [groupName,setGroupName]=useState("");
  const category=useMutation({mutationFn:()=>createCategory(planId,newClientId(),{name,group_id:group||null}),onSuccess:async()=>{setName("");await onSaved();}});
  const groupMutation=useMutation({mutationFn:()=>createCategoryGroup(planId,newClientId(),groupName),onSuccess:async()=>{setGroupName("");await onSaved();}});
  return <details className="budget-composer"><summary>+ Add categories & groups</summary>
    <form onSubmit={e=>{e.preventDefault();category.mutate();}}><label>Category name<input value={name} onChange={e=>setName(e.target.value)} required /></label><label>Group<select value={group} onChange={e=>setGroup(e.target.value)}><option value="">Other categories</option>{groups.filter(g=>g.status==="active").map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select></label><button type="submit" disabled={category.isPending || !name.trim()}>Add category</button></form>
    <form onSubmit={e=>{e.preventDefault();groupMutation.mutate();}}><label>New group name<input value={groupName} onChange={e=>setGroupName(e.target.value)} required /></label><button type="submit" disabled={groupMutation.isPending || !groupName.trim()}>Add group</button></form>
    {(category.isError || groupMutation.isError) && <p role="alert">{message(category.error ?? groupMutation.error)}</p>}
  </details>;
}
