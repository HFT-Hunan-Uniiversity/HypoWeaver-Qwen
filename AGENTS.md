# Repository operating boundary

- Treat `backend/var/`, `output/`, imported datasets, runtime databases, receipts, and local credentials as private runtime state. Do not commit them.
- Do not recursively scan drive roots, user profiles, or system temporary directories. Keep discovery inside this repository and explicitly named upstream evidence folders.
- Do not create Git worktrees outside this repository without explicit user approval.
- Preserve the frozen Group 1 handoff as read-only evidence. Any scientific-boundary change must be returned to Group 1 rather than silently rewritten in Group 2.
- A run may be called scientifically executed only when it uses registered immutable datasets, a non-fixture executor, independent reproduction, and claim-gate evidence. Plan-only runs must remain clearly labelled.
- Keep generated artifacts bounded and reproducible; clean test-only temporary directories after validation.

