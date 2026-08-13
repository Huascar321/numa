# Design

Represent one transfer operation with two linked legs in one transaction. Same
currency legs have equal absolute amounts. Cross-currency transfers retain both
originals, derived rate, source, and timestamp. Reversal appends linked history.
