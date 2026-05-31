- Files should be organized by single responsibility (one clear purpose per file).
- Prefer modular design over large monolithic files.

- Soft thresholds (not strict rules):
  - > 500 lines: review for potential refactoring
  - > 800 lines: strong signal that the file likely contains multiple responsibilities
  - > 1000 lines: refactoring should be actively considered unless there is a justified exception

- Line count is a heuristic, not a rule. Architectural clarity always takes priority.

- Do NOT split files artificially just to reduce line count.
  Only split when there is a meaningful separation of concerns.

- Good reasons to split a file:
  - Multiple unrelated responsibilities
  - Different domain concepts mixed together
  - Reusable logic hidden inside a large module
  - Difficult navigation or understanding of the file
  - High coupling between independent components

- Avoid over-splitting:
  - Do not create micro-files with no real standalone meaning
  - Avoid fragmentation that increases cognitive overhead

- Prefer grouping by domain or feature:
  - domain/
  - services/
  - infrastructure/
  - adapters/
  - features/

- Aim for high cohesion and low coupling across the codebase.