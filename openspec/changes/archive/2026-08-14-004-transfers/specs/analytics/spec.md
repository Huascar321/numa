# Analytics delta

## MODIFIED Requirements

### Requirement: Explicit reporting boundaries
Analytics MUST classify Transfer roots and legs as transfers and exclude both
legs, including cross-currency and reversal legs, from income, expense, and net
totals. Analytics MAY display a grouped Transfer separately with both originals
and rate evidence, but MUST not aggregate it or treat it as unconverted income
or expense. This change introduces no analytics aggregation or currency
conversion implementation.

#### Scenario: Mixed-currency report
- **GIVEN** a report includes a transfer and an unconverted amount
- **WHEN** totals are computed
- **THEN** the transfer MUST be excluded and unconverted state MUST be visible.

#### Scenario: Exclude a grouped Transfer from net reporting
- **GIVEN** a reporting period contains income, expense, and a cross-currency Transfer
- **WHEN** analytics income, expense, and net totals are calculated
- **THEN** only the income and expense movements affect those totals, while the Transfer remains separately identifiable as a grouped excluded operation.
