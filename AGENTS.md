# Agent collaboration rules

## Issue-first workflow

Use `implementation-plan.md` as the task backlog and `plan.md` for architecture and scope. Task IDs identify work across the checklist, GitHub issues and PRs.

Before implementing a task:

1. Search existing open and closed GitHub issues and PRs for its task ID. Reuse the existing issue; do not create duplicate work or redo completed work.
2. If no issue exists, create one with the task ID and title, scope, completion criteria, dependencies and effort estimate from the checklist. Create issues as needed; there is no need to create the entire backlog at once.
3. Verify the issue is assigned to the requesting teammate and marked **In progress** before editing implementation files. If another teammate has claimed it or an active PR already covers it, report the conflict and do not implement it.
4. Confirm required dependencies are complete. Agreed fixtures may unblock explicitly scoped UI/adapter development, but do not count mocked flows as completed integration.
5. Use a task branch, such as `feat/F03-fastapi-template`, and open a linked draft PR early. Include the task ID in the PR title and `Closes #<issue-number>` in its description.

Assignment is the shared claim, not a local checkbox. When there is a simultaneous claim or uncertainty about ownership, resolve it before implementation. If GitHub access or the teammate's GitHub identity is unavailable, ask the user to verify/create the claim; do not assume it is unassigned.

Agents may create the issue needed for an explicitly assigned task as part of this workflow. Do not independently choose additional tasks, assign work to other teammates, or create the full issue backlog without a user request.

## Branch naming

- All new branches must use a purpose-based prefix such as `feat/`, `fix/`, `docs/`, `refactor/`, `test/` or `chore/`.
- Never create a branch with the `codex/` prefix, including branches created by agents or automated tools.
- For backlog tasks, include the task ID and a short description, for example `feat/P02-document-worker` or `docs/P02-completion`.
- Existing branches may keep their names; this rule applies to every branch created after this instruction is added.

## Scope and shared files

- Work only on the task explicitly assigned by the user. Record unexpected work as a suggested follow-up task rather than expanding scope silently.
- Coordinate overlapping edits to API/event contracts, root Compose files, frontend routing/configuration and infrastructure. Separate branches do not prevent duplicate effort or incompatible interfaces.
- Keep service-specific migrations and feature routes local to their service/feature. Follow the agreed contracts and independent service boundaries.
- Provide a short verification note and document configuration/setup changes in the PR. Use the focused prototype checks from the plan.

## Code simplicity

- Keep code simple, clear and easy to follow. Avoid convoluted logic and unnecessary abstractions.
- Split code into clean, focused files when it improves readability and maintainability.

## Completion

- Keep the issue **In progress** until the PR is merged and its completion criteria are met. Do not close it merely because an agent finished a local change.
- After merge, close the issue and check off the matching backlog task. GitHub issues are the shared source of current assignment/status; the checklist tracks the planned deliverables.
- For blocked work, record the blocker on the issue. Release/reassign a claim only with the current owner's agreement; do not silently take over another teammate's task.
