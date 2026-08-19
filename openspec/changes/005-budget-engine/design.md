# Design

Calculate month envelopes deterministically. Positive Category Available rolls
into the next month. Cash/Bank overspending reduces the following month's Ready
to Assign; Credit Card overspending becomes implicit negative card debt instead
of remaining in the Category.

For mixed categories, classify financing and excess by event time, using the
transaction ID as the deterministic tie-breaker. Credit Card purchases are
expenses; payments are Transfers excluded from expense totals, with no payment
categories or automatic category movement.

Keep purchases and card debt in the Account's native currency. A differing
reporting currency remains unconverted; cross-currency payments retain both
originals and explicit Transfer rate evidence. Goal status follows target
balance, monthly funding, or due-date funding rules; the current month counts
as a remaining month, and a goal due this month or overdue requires its full
remaining shortfall as the contribution.
