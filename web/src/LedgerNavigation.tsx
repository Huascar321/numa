const sections = [
  ["transactions-heading", "Activity"],
  ["transfers-heading", "Transfers"],
  ["reconciliation-heading", "Reconciliation"],
  ["taxonomy-heading", "Categories"],
] as const;

export function LedgerNavigation() {
  return <nav className="section-navigation" aria-label="Ledger sections">
    <span className="section-navigation-caption">Jump to</span>
    {sections.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}
  </nav>;
}
