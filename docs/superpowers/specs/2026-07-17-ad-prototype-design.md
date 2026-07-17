# Ad-placement UX prototype (design)

**Date:** 2026-07-17 · **Status:** approved (PM, this date)

## Goal

A **firewalled, non-monetizing** AdMob **test** banner anchored at the bottom of the signed-in
shell, **off by default**, so the PM can feel the placement and observe real ad load/perf before
committing to the launch ad design. This is a UX/perf prototype — **not** live ads. Live/monetizing
ads remain gated on E0 (OAuth verification) per D21 and the AGENTS scope boundary.

## Scope decision (recorded)

AGENTS.md scope boundary says "the ad layer itself — only after the email engine ships and verifies."
Moving up a **firewalled, non-monetizing, test-creative, flag-off-by-default** prototype is a
deliberate PM exception to that boundary — it validates UX/perf without premature monetization and
cannot cross the Limited-Use line (no content, test creatives, never shipped by default). Log as a
decision (Dn) alongside this spec. D19 (THE FIREWALL) and D21 are **unchanged**.

## Components

### 1. `lib/ads/ad_banner_slot.dart` (new) — the banner widget

- A `StatefulWidget` that loads a `google_mobile_ads` `BannerAd` (`AdSize.banner`, 320x50) using
  Google's **public test ad unit** and npa=1 via the existing `AdConfig.nonPersonalizedRequest()`.
- Test ad unit ids (Google's public test units — safe, never monetize):
  - Android: `ca-app-pub-3940256099942544/6300978111`
  - iOS: `ca-app-pub-3940256099942544/2934735716`
- Reserves a **fixed 50 logical-px height at all times** (a `SizedBox(height: 50)` container),
  even before/without fill, so agenda/calendar content never reflows when the ad loads.
- FIREWALL (D19): imports **nothing** from feature/content modules; takes **no** parameters
  derived from email/event/child/category data. Renders a banner and nothing else.
- Disposes the `BannerAd` in `dispose()`.

### 2. `lib/ads/ad_config.dart` (existing) — extend

- Keep `nonPersonalizedRequest()`.
- Add `bannerAdUnitId` (platform-switched test id) and a static `adsEnabled`
  (`bool.fromEnvironment('SHOW_ADS', defaultValue: false)`), so the flag + ids live in the one
  isolated ad file, not scattered. `adsEnabledProvider` (§3) wraps `adsEnabled` for testability.

### 3. `adsEnabledProvider` (new, in `lib/core/providers.dart`) — testable gate

- `final adsEnabledProvider = Provider<bool>((_) => AdConfig.adsEnabled);` — the one seam the
  widget test overrides (dart-define is compile-time and can't be flipped at runtime otherwise).
  Production reads the real flag; tests use `ProviderScope(overrides: [adsEnabledProvider.overrideWithValue(true/false)])`.

### 4. `lib/ui/home_shell.dart` (modify) — anchor the slot

- `HomeShell` is already a `ConsumerStatefulWidget`; in `build`, `final showAds = ref.watch(adsEnabledProvider);`.
- Wrap the `Scaffold.body` in a `Column`:
  `Column(children: [Expanded(IndexedStack(Agenda|Calendar)), if (showAds) const AdBannerSlot()])`.
- The `NavigationBar` stays as `bottomNavigationBar`. The banner sits between content and nav.
- When `showAds` is false the slot is not built at all.

### 4. `lib/main.dart` (modify) — conditional SDK init

- If `AdConfig.adsEnabled`: `await MobileAds.instance.initialize()` before `runApp` (best-effort,
  wrapped so a failure never blocks launch — same posture as Firebase init).
- If disabled: never touch the SDK → zero startup cost, app behaves exactly as today.

## Gating

`--dart-define=SHOW_ADS=true` (default **false**), read once in `AdConfig.adsEnabled`
(`bool.fromEnvironment('SHOW_ADS', defaultValue: false)`). Off unless explicitly built with the
flag, so a stray build can never surface ads. Matches the existing `API_BASE_URL` /
`GOOGLE_IOS_CLIENT_ID` dart-define pattern.

- **Test distribution** (what testers get): build **with** `--dart-define=SHOW_ADS=true` so the
  banner is visible and testers see ads working.
- **Everyday dev / a default build:** omit the flag → no ads, app behaves exactly as today.

To run it: `flutter run … --dart-define=SHOW_ADS=true` (plus the usual API/client-id defines).

## Distribution & launch path (decided 2026-07-17)

- **Now (this spec):** the banner serves Google's **test** ad units. Testers see a working ad;
  **no AdMob account, no cost, no invalid-traffic ban risk.** Test ads render through the real
  SDK, so load/latency/layout/perf are representative.
- **Never:** real (advertiser) ads shown to testers — AdMob treats that as invalid traffic and
  can suspend the account. Real ads only serve to real users, post-launch.
- **At launch (documented follow-up, NOT built here):** a ~30-min swap — create the real AdMob
  account, register the app, replace the test **App ID** (manifest + `Info.plist`) and the test
  **ad-unit IDs** (`AdConfig`) with real ones, add a `RequestConfiguration` test-device list so
  internal devices still get test ads, publish `app-ads.txt` at the (E0) domain, and add an
  **AdMob sub-processor row to the privacy policy** (mirrors the Firebase/FCM row). Real serving
  additionally needs the domain + a published, AdMob-reviewed app.

## Platform config (already present — no change)

- Android `AndroidManifest.xml`: AdMob test **app** id `ca-app-pub-3940256099942544~3347511713` ✓
- iOS `Info.plist` `GADApplicationIdentifier`: `ca-app-pub-3940256099942544~1458002511` ✓

## Error / empty handling

- Ad fails to load (no network, no fill) → the reserved 50px slot stays blank and does not error;
  no crash, nothing user-facing. `onAdFailedToLoad` just logs nothing user-facing and leaves the
  slot empty.
- SDK init failure → caught, app continues (banner simply never fills).

## Firewall (D19) — how it stays safe

- The new file is under `lib/ads/`; `scripts/firewall-guard.sh` blocks any `lib/ads/` file that
  references `event|child|extraction|email_body|email_content|category`. Enforced on every edit.
- `HomeShell` passes the slot **no** content-derived data (it takes no such params).
- The existing bidirectional ad-isolation test is extended to cover `ad_banner_slot.dart`.

## Testing

- Widget test: with `adsEnabledProvider` overridden **false** (default), `HomeShell` builds **no**
  `AdBannerSlot` (find none). Override it **true** and assert the slot **is** present. (The real
  `BannerAd` needs platform channels, so the test overrides `adsEnabledProvider` and asserts the
  slot widget's presence/absence — it does not attempt to load a live ad.)
- Firewall/isolation: extend the ad-isolation test so `lib/ads/ad_banner_slot.dart` is asserted
  free of feature/content imports (and `lib/ads/` remains the only place importing
  `google_mobile_ads`).
- The live SDK banner render itself is **not** unit-tested (needs a platform) — that's the
  on-device eyeball this prototype exists for.

## Out of scope (YAGNI)

Real/production ad units; any monetization; the paid ad-free tier (D21); personalized ads;
interstitials; frequency capping; inline-list ad cards; a settings toggle. All are Track E proper,
post-E0.
