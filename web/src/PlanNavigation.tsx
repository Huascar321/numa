import { NavLink } from "react-router";
import "./navigation.css";

const destinations = [
  { path: "budget", label: "Budget" },
  { path: "accounts", label: "Accounts" },
  { path: "ledger", label: "Ledger" },
  { path: "gmail", label: "Gmail" },
] as const;

export function PlanNavigation({ planId }: { planId: string }) {
  return <nav className="plan-navigation" aria-label="Plan navigation">
    {destinations.map(({ path, label }) => <NavLink
      key={path}
      to={`/plans/${planId}/${path}`}
      className="plan-navigation-link"
      end
    >{label}</NavLink>)}
  </nav>;
}
