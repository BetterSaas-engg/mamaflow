# Test plan — tiers, multi-mailbox, Family sharing

Covers PR #20 (D44/D45/D46) plus the fixes that shipped just before it (sync window D40,
dormant skip D41, Android OAuth D43). Written 2026-08-05.

**Read the priorities literally.** P0 is "existing testers broke" — a regression here is worse than
any new feature not working, because it silently stops mail flowing for people already using the app.
P1 is the new paid functionality. P2 is nice-to-confirm.

---

## 0. Before you touch anything: record the baseline

Two numbers make everything afterwards interpretable. Without them you can't tell a fix from a
coincidence.

1. **Anthropic Console → current month spend.** Write down today's $/day.
2. **Item counts per tester**, so you can prove nothing was lost:

```sql
SELECT u.email, COUNT(i.id) AS items
FROM users u LEFT JOIN items i ON i.user_id = u.id AND i.deleted_at IS NULL
WHERE u.deleted_at IS NULL GROUP BY u.email ORDER BY u.email;
```

---

## 1. Deploy (P0)

Merge PR #20. Railway deploys `main` and runs `alembic upgrade head`, applying three migrations:
`b2e7c419d5aa` (users.tier) → `c9f4a2b81e37` (mail_connections) → `e1a7b3c95d24` (households).

**Success:** the deploy goes green and `GET /health` responds.

**The one thing that must be true afterwards** — every existing user got a mailbox row. Sync reads
mailboxes from `mail_connections` now, so a user without one silently stops syncing:

```sql
SELECT u.email, u.tier, c.provider, c.email AS mailbox
FROM users u LEFT JOIN mail_connections c
  ON c.user_id = u.id AND c.deleted_at IS NULL
WHERE u.deleted_at IS NULL ORDER BY u.email;
```

**Success:** every active user has exactly one mailbox row, matching the address they signed in with,
and `tier = 'free'`.

**Failure:** any row with `mailbox` NULL. Stop and tell me — that user's mail has stopped syncing.

**If the deploy fails on migrations:** it will say "Can't locate revision". That means the DB is ahead
of or behind the code; send me the exact message rather than retrying.

---

## 2. P0 — did anything break for existing testers?

Do this **before** touching tiers. These are the regressions that would matter most.

### 2.1 Sync still works
Open the app as an existing tester → pull to refresh / Sync now.

- **Success:** sync completes, items still there, count ≥ your baseline from §0.
- **Failure:** "Please sign in again" (credential lost in the migration), or items disappeared.

### 2.2 The sync-window fix is doing its job
This was the bug where anything older than the newest 50 emails was **never** processed. On a busy
inbox you should now see a backlog drain over successive syncs.

```sql
SELECT u.email, COUNT(*) FROM synced_messages s
JOIN users u ON u.id = s.user_id WHERE s.deleted_at IS NULL
GROUP BY u.email;
```

Run it, sync a few times over an hour, run it again.

- **Success:** the number climbs on a busy inbox and settles; new events appear that predate the last
  50 messages.
- **Watch for:** it climbing by exactly 50 forever with no new items — tell me, that's the blocked-
  sender starvation I fixed, resurfacing.

### 2.3 Cost has not regressed
Check Anthropic spend ~24h after deploy.

- **Success:** roughly flat or lower vs your §0 baseline. Multi-mailbox shares one per-run budget
  across mailboxes, so it should *not* scale with mailboxes connected.
- **Failure:** any climb. Send me the number — a jump means the shared cap isn't holding.

### 2.4 Reminders still arrive
Wait for the daily digest push.

- **Success:** arrives as before with tomorrow's events.

---

## 3. P0 — Android OAuth (the bug you reported)

**Device: your S25 Ultra.** This is the half I could not verify without you — I proved the redirect
now reaches the app, but not a real end-to-end Google consent.

1. Install the new build.
2. Sign out if signed in.
3. Tap **Continue with Google**.
4. **You should first see a disclosure screen** ("Before you connect Gmail") — read it, this is the
   wording I've asked you to sign off. Tap **I agree, continue**.
5. Complete Google consent in the browser.

- **Success:** the browser closes and you land **inside the app, signed in**. This is the exact thing
  that used to fail.
- **Partial success worth reporting:** you land in the app but it shows the sign-in screen again —
  that means the redirect arrived but the recovery didn't complete. Tell me; it's a different fix.
- **Failure:** you're stranded in Chrome, as before.

**To make it a real test of the fix, force the hard case:** after tapping "I agree, continue" and
reaching Google's page, switch to another heavy app (camera, maps) for ~30 seconds, then come back and
finish consent. That's what makes Android kill our process — the actual bug. Success is the same:
you end up signed in.

**Also test "Not now"** on the disclosure: it should just return you to sign-in with no error.

---

## 4. P1 — Tiers and mailboxes

Nothing assigns tiers yet, so set them by hand. From the Railway shell (or locally with
`DATABASE_URL` pointed at the Railway DB):

```bash
python -m api.db.set_tier --list                      # see everyone's tier
python -m api.db.set_tier you@example.com pro
python -m api.db.set_tier partner@example.com family
```

### 4.1 Free tier is capped at 1
As a free tester: **Settings → Email accounts**.

- **Success:** header reads "Free plan", "1 of 1 email accounts connected", and "Add another email"
  is **greyed out** with text explaining the plan includes 1 and offering to disconnect one.
- **Failure:** the add button is tappable, or the count is wrong.

### 4.2 Pro can connect a second mailbox
Set yourself to `pro`, reopen Settings → Email accounts (pull to refresh).

- **Success:** "Pro plan", "1 of 2", **Add another email** is tappable.
- Add a second mailbox (Yahoo/iCloud with an app password, or a second Gmail).
- **Success:** it appears in the list; the count becomes "2 of 2"; add is greyed out again.
- **Then sync.** **Success:** events from the *second* mailbox appear in the calendar.
- **Failure to report:** the second mailbox connects but never produces events.

### 4.3 Disconnect frees the slot
Tap the unlink icon on one mailbox.

- **Success:** confirmation says the stored password will be deleted and existing events stay; after
  confirming, the count drops and "Add another" is available again. **Existing events remain in the
  calendar.**

### 4.4 Wrong app password
Try adding a mailbox with a deliberately wrong password.

- **Success:** a clear message about needing an *app password*, not the account password. No mailbox
  is added.

---

## 5. P1 — Family sharing (needs two phones / two accounts)

Set the **owner** to `family`. The second parent can stay on their own account (they inherit the
plan).

1. Owner: **Settings → Family sharing → Invite my partner** → an 8-character code appears.
2. Partner: **Settings → Family sharing → I have a code** → read the dialog, enter the code, Join.

- **Success at step 2:** the dialog says joining shares the events found in your email, and that your
  inbox and password stay private. **This is the consent moment — check the wording reads honestly
  to you.**
- **Success after joining:** both phones show both people's events in one calendar; the member list
  shows both, with the owner marked "Plan owner".
- **Success on the boundary:** the partner's **Email accounts** screen shows only *their own*
  mailboxes — never the owner's. This is the line that must not move.

### 5.1 Either parent can action an item
Mark one of the *other person's* events done.

- **Success:** it updates for both.

### 5.2 Reminders cover the shared calendar
Wait for the next digest.

- **Success:** tomorrow's digest includes the partner's events too.

### 5.3 Codes behave
- Ask for a code twice → **only the newest works** (the first is superseded).
- Try a made-up code → refused with "That code isn't valid".
- Try joining while already in a household → refused.

### 5.4 Stop sharing
Owner removes the partner (or partner removes themselves).

- **Success:** each immediately sees only their own events again, and **nothing is deleted** — both
  keep their own items.

### 5.5 The one I most want confirmed
Partner **deletes their account**, then **signs back in with the same email**.

- **Success:** they come back as a *fresh solo account* — they do **not** see the owner's calendar.
- **Failure:** they can see the owner's events. Stop and tell me immediately; that's the cross-user
  bug the audit caught and it would mean my fix didn't hold in production.

---

## 6. P2 — worth a look

- **Free tester sees ads placeholder / paid doesn't** — `ads_enabled` is served by the API but the ad
  layer is still gated on E0, so this is informational only.
- **Dormant skip** can't really be tested in a week (14-day threshold). Confirmed by tests instead.

---

## What to send me

For anything that fails, the most useful thing is:

1. **What you did**, in order, and what you expected.
2. **The exact on-screen message** (screenshot is fine).
3. For backend suspicions, the Railway logs around that minute — the sync log line is one row per
   sync and looks like `sync: user=<id> model=... calls=N gate_skipped=N ... backlog=N`.
4. For cost, the Anthropic Console daily number, not an impression.

Please don't pre-diagnose — "sync stopped after I added a second mailbox" is more useful than a guess
at which layer broke.

## Definition of done for this round

- Every existing tester still syncing, item counts ≥ baseline (§2.1)
- Cost flat or lower 24h after deploy (§2.3)
- Android Google sign-in lands **inside the app**, including the backgrounded case (§3)
- Pro connects and syncs a second mailbox (§4.2)
- Family: both parents see one calendar, and neither can see the other's mailboxes (§5)
- Delete-and-return does **not** restore sharing (§5.5)

Hit those and the tier work is proven; the remaining gap before it is sellable is billing.
