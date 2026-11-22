import { ReactNode, useEffect, useRef } from "react";
import { Link, NavLink, Outlet, useLocation, useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Account, Plan, getAccounts, getPlan } from "./api";
import { formatMoney } from "./money";
import "./budget.css";
import "./workspace.css";

export function WorkspaceFrame({plan, accounts, children}: {plan:Plan;accounts:Account[];children:ReactNode}) {
  const location = useLocation();
  const content = useRef<HTMLDivElement>(null);
  const previousPath = useRef(location.pathname);
  const archived = accounts.filter((account) => account.status === "archived");
  useEffect(() => {
    if (previousPath.current !== location.pathname) {
      previousPath.current = location.pathname;
      window.scrollTo?.({ top:0, behavior:"instant" });
      content.current?.focus({preventScroll:true});
    }
  }, [location.pathname]);
  return <div className="budget-workspace workspace-shell">
    <a className="workspace-skip" href="#workspace-content">Skip to content</a>
    <aside className="budget-sidebar" aria-label="Budget accounts">
      <Link to="/plans" className="budget-plan-name"><span className="eyebrow">Your plan</span><strong>{plan.name}</strong><span>Switch plan ↗</span></Link>
      <nav aria-label="Workspace navigation">
        <NavLink to={`/plans/${plan.id}/budget`}><span aria-hidden="true">◫</span><span>Budget</span></NavLink>
        <NavLink to={`/plans/${plan.id}/ledger`}><span aria-hidden="true">≡</span><span>All activity</span></NavLink>
        <NavLink to={`/plans/${plan.id}/accounts`}><span aria-hidden="true">▤</span><span>Accounts</span></NavLink>
        <NavLink to={`/plans/${plan.id}/gmail`}><span aria-hidden="true">✉</span><span>Gmail</span></NavLink>
      </nav>
      <div className="budget-account-list">
        <h2>Cash & wallets</h2>
        {accounts.filter(a=>a.account_type!=="Credit Card" && a.status==="active").map(a=><AccountLink key={a.id} account={a} planId={plan.id} />)}
        <h2>Credit cards</h2>
        {accounts.filter(a=>a.account_type==="Credit Card" && a.status==="active").map(a=><AccountLink key={a.id} account={a} planId={plan.id} />)}
        {archived.length > 0 && <details className="budget-closed">
          <summary>Closed accounts <span>{archived.length}</span></summary>
          {archived.map(a=><AccountLink key={a.id} account={a} planId={plan.id} />)}
        </details>}
        <Link className="budget-add-account" to={`/plans/${plan.id}/accounts`}>+ Manage accounts</Link>
      </div>
      <p className="budget-sidebar-note">{plan.reporting_currency_code} budget<br />Other currencies stay separate.</p>
    </aside>
    <div ref={content} id="workspace-content" className="budget-main workspace-content" tabIndex={-1}>{children}</div>
  </div>;
}

function AccountLink({account,planId}:{account:Account;planId:string}) {
  const { search, pathname } = useLocation();
  const active = pathname.endsWith("/ledger") && new URLSearchParams(search).get("account")===account.id;
  return <Link className={`budget-account ${account.status === "archived" ? "is-archived" : ""}`} aria-current={active?"page":undefined} to={`/plans/${planId}/ledger?account=${account.id}`}><span>{account.name}</span><span>{formatMoney(account.balance.amount, account.currency_code)}</span></Link>;
}

export function WorkspaceLayout() {
  const {planId=""}=useParams();
  const plan=useQuery({queryKey:["plans",planId],queryFn:()=>getPlan(planId)});
  const accounts=useQuery({queryKey:["plans",planId,"accounts"],queryFn:()=>getAccounts(planId)});
  const fallback:Plan={id:planId,name:"Your plan",reporting_currency_code:"",created_at:"",updated_at:""};
  return <WorkspaceFrame plan={plan.data ?? fallback} accounts={accounts.data ?? []}>
    {plan.isError && <div className="workspace-feedback"><p role="alert">This Plan could not be loaded.</p><button onClick={()=>void plan.refetch()}>Retry Plan</button><Link to="/plans">Back to Plans</Link></div>}
    {!plan.isError && <Outlet context={{workspace:true}} />}
  </WorkspaceFrame>;
}
