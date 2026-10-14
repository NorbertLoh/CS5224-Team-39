# U06 doctor availability fixture editor

Sign in with an active doctor membership and open `/doctor` (Doctor in the role
navigation). Existing `/doctor/clinics/:tenantId` routes mount the same explicitly
labelled fixture preview after the shell's membership check. Demo clinic/doctor
selection is independent of the signed-in account and selected real clinic.
It never reads or writes scheduling APIs.

## Code layout

- `AvailabilityEditor.tsx` owns editor state and coordinates feature components.
- `FixtureSelectors.tsx` contains the preview notice and demo account selectors.
- `TimetableToolbar.tsx` contains week navigation, the legend and instructions.
- `WeeklyTimetable.tsx` renders the week grid; `TimetableCell.tsx` renders each
  slot's state and appearance.
- `useTimetableSelection.ts` handles pointer gestures, keyboard navigation and
  selection changes.
- `SelectionActions.tsx` renders the selected count and add/remove/clear buttons.
- `timetable.ts` contains pure date, selection and batch-edit operations;
  `fixtures.ts` supplies fixture data and slot validation.

The feature and its tests are formatted with Prettier 3.6.2 using single quotes
and no semicolons. To check formatting from `apps/web` without adding a dependency:

```sh
npm exec --yes --package=prettier@3.6.2 -- prettier --check "src/features/availability/**/*.{ts,tsx}" tests/availability.test.ts --single-quote --no-semi
```

## Running the preview

Run the frontend with the existing `npm run dev` setup. Authentication/identity
services are still needed for the protected doctor workspace; no extra environment
variables or services are required by the editor.

The editor uses the shared synthetic dataset in `dev/fixtures/telelink.json`.
Slots move by whole days so the earliest fixture day is tomorrow in Singapore.
Active fixture doctor memberships determine the choices. Changes are kept in
component memory across demo clinic/doctor selections and reset on page reload.
There is no simulated save to a server or durable browser persistence.

The editor displays a Monday–Sunday timetable in Singapore time with 48 half-hour
rows per day. Previous/next week and This week controls change the visible dates.
The grid initially scrolls to morning; scroll vertically for all 24 hours and
horizontally on narrow screens for the remaining days.

Drag vertically to select a time range or horizontally to repeat the range across
days, then choose Add availability or Remove availability. Each new drag adds a
separate rectangle of half-hour cells when it starts on an unselected cell,
preserving earlier selections. Starting on a selected cell instead deselects the
dragged rectangle. The gesture's mode stays fixed until release. Shrinking or
reversing the drag restores cells outside its current rectangle. Overlapping
ranges are combined so each cell is counted and applied once; gaps remain empty.
Clicking a selected cell deselects only that cell, including where ranges overlap.
Enter/Space toggles a cell, arrows move focus, Shift + arrows
extend the range, and Escape clears it. Pointer capture supports releasing outside
the grid, and cancelled gestures restore the selection before the drag. Touch dragging is supported
on cells; use the time gutter or scrollbar to scroll without selecting.

Every added cell becomes a future 30-minute UTC interval. Overlaps are rejected
for that doctor across both clinics, while adjacent intervals are allowed.
Other-clinic slots are shown in purple, unavailable slots in grey and available
slots in green. Removal affects the selected doctor's overlapping slots in the
selected clinic, including fixture slots starting between half-hour boundaries.
Unavailable, past and other-clinic slots cannot be removed. Range operations are
atomic: any conflict leaves all slots unchanged. Clear selection cancels without
editing. Data loads synchronously from the bundled fixture, so the editor does
not simulate network loading or failures.

Verification (14 October 2026): all 43 tests passed with `npm test`;
`npm run lint` and `npm run build` (including TypeScript) passed from `apps/web`.
Focused tests cover timezone conversion, invalid dates, interval boundaries,
cross-clinic conflicts, membership choices, removal protection, reverse rectangular
ranges across month boundaries and atomic range failure. Local browser checks
passed for dragging six cells across two days, adding the range, selecting two
cells using the keyboard and removing them. Separate keyboard selections and
consecutive disjoint drags were also verified; adding both ranges preserved the
gap between them. Pointer deselection preserved the neighbouring selected cell,
and keyboard deselection of the last cell disabled the actions. Focused tests
cover deselecting corners, edges and interior cells of overlapping rectangles,
drag erasure, fixed gesture mode and restoration when shrinking a drag. Browser
drag deselection removed the middle two cells of a four-cell selection, retaining
the cells above and below. After the component refactor, keyboard selection,
drag deselection, separate drag selection and applying the combined selection
were rechecked successfully in the local browser.
Live scheduling integration remains
separate; S07 replaces
fixture data and client-side validation with authenticated scheduling API calls
and authoritative server conflicts.
