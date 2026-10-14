# U07 clinic booking

Open a clinic, click Book, choose a date and an available 30-minute slot, then
continue to checkout. Patient sign-in is required. Clinic and doctor information
come from the existing real tenant API; the slot/hold/checkout adapter is an
explicit fixture preview. No payment is taken and no real appointment is created.

The demo schedule projects the available/unavailable pattern and 30-minute
duration from `dev/fixtures/telelink.json` onto the selected clinic's doctors for
the next three Singapore dates. It is independent of U06's availability preview.
S07 replaces this adapter with scheduling APIs; B07 connects billing checkout.
U09 owns payment return/result screens. Reloading clears the local selection/hold.

No new configuration. Existing local clinic backend and frontend setup applies.
Run frontend tests, lint and build. Review the clinic-to-Book link, date changes,
disabled occupied slots, checkout details and exact hold-expiry boundary.
