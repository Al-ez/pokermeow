# PokerMeow engineering rules

- The server is authoritative for all game state.
- Do not duplicate poker rules in the GUI or networking layer.
- Reuse existing game-engine methods rather than reimplementing calculations.
- Keep game engine, networking, controller, and presentation logic separated.
- Before adding a helper, search for an existing equivalent.
- Remove obsolete implementations after replacing them.
- Avoid duplicate Qt signal connections and unnecessary full-table rerenders.
- Preserve network protocol compatibility unless explicitly instructed otherwise.
- Add or update tests for every behavioural change.
- Run the relevant tests after modifications.
- Keep files focused; propose extraction when a module becomes oversized.
