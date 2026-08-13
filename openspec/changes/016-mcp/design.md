# Design

Expose get_plan_summary, list_category_balances, search_transactions,
get_exchange_quotes, and get_import_status through strict semantic schemas with
bounded pagination. Annotate readOnly/destructive/idempotent, redact by default,
reject arbitrary SQL/filesystem/HTTP, and expose no secrets. Auth mode is
**UNVERIFIED**.
