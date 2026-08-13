# Design

Flow parser → normalize → matching → dry run → review → commit. Support UTF-8
BOM, CRLF, semicolon, preamble/header/footer, exact eight-field header,
DD/MM/YYYY, HH:MM:SS, decimal dot, comma grouping, optional signs, quoted
descriptions, row/order, and compound source identity. Arithmetic/count mismatch
is warning/block by explicit policy, never invented reconciliation. Four
consecutive April–July samples verify the shape, footer counts, and balance
chain. `SALDO ACTUAL` is stored as current/as-of-export balance, not period
ending balance. Interest/IVA rows may reuse an ID, so source row/order is part
of identity; rows are not reordered before chain validation. Additional
account/export versions and embedded semicolon, escaped-quote, or multiline
variants **REQUIRES REAL SAMPLE**.
