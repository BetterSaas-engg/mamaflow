# Ad-placement UX Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A firewalled, flag-gated AdMob **test** banner anchored at the bottom of the signed-in shell, so testers can see ads working and the PM can judge placement/perf before launch.

**Architecture:** All ad-SDK code stays inside `lib/ads/` (the firewall boundary the isolation test enforces). A new `AdBannerSlot` widget renders a fixed-height test banner; `AdConfig` gains the test ad-unit id + SDK init; a `SHOW_ADS` dart-define (read via `adsEnabledProvider` in `lib/core/`, so nothing outside `lib/ads/` imports the SDK) gates whether the slot and SDK init happen at all.

**Tech Stack:** Flutter, Riverpod, `google_mobile_ads` ^9.0.0, flutter_test.

## Global Constraints

- **THE FIREWALL (D19):** the ad slot takes ZERO content/event/child/email/item data. The string `google_mobile_ads` must appear ONLY under `lib/ads/`. Files under `lib/ads/` must not import `package:mamaflow/…` or `import '../…'`, and must not contain the words `event|child|extraction|email|item` (the existing `test/ads/ad_isolation_test.dart` enforces all of this and auto-covers new `lib/ads/` files).
- **Non-personalized (D21):** all ad requests use `AdConfig.nonPersonalizedRequest()` (npa=1).
- **Off by default:** `const bool.fromEnvironment('SHOW_ADS', defaultValue: false)`. No flag → no slot, no SDK init, app behaves exactly as today.
- **Test creatives only:** Google public test ad units. Android banner `ca-app-pub-3940256099942544/6300978111`, iOS banner `ca-app-pub-3940256099942544/2934735716`. Test **app** ids are already in the Android manifest + iOS Info.plist — do NOT change them.
- Run frontend tests from `frontend/` with `flutter test`; `flutter analyze` must stay clean.

---

### Task 1: Refine the firewall guards for Flutter widgets under `lib/ads/`

**Why:** Flutter's structural `child:` parameter matches the bare-word `child` firewall term, so the guard blocks *any* widget under `lib/ads/`. Narrow the term to the actual content field (`child_name`/`childName`) — precise to real content, without weakening the structural firewall (the "no app/content imports under `lib/ads/`" checks are untouched and remain the real guarantee). PM-approved 2026-07-17.

**Files:**
- Modify: `scripts/firewall-guard.sh`
- Modify: `frontend/test/ads/ad_isolation_test.dart`

**Interfaces:** none (guardrail refinement).

- [ ] **Step 1: Refine `scripts/firewall-guard.sh`** — in the ad-layer rule (rule 3), both the detecting `if grep` and the printing `grep … | sed` use the same pattern. Change **both** occurrences of:

```
\b(event|child|extraction|email_body|email_content|category)\b
```
to:
```
\b(event|child_name|childName|extraction|email_body|email_content|category)\b
```

- [ ] **Step 2: Refine `frontend/test/ads/ad_isolation_test.dart`** — change the content-word regex in the "every file under lib/ads/ stays app- and content-free" test from:

```dart
      RegExp(r'\b(event|child|extraction|email|item)s?\b',
```
to:
```dart
      RegExp(r'\b(event|child_name|childName|extraction|email|item)s?\b',
```

- [ ] **Step 3: Verify the guard now allows `child:` but still blocks `child_name`**

```bash
cd /Users/sabiranthapa/Desktop/mamaflow
# (a) a widget using Flutter's child: must now PASS
printf 'import "package:flutter/material.dart";\nclass P extends StatelessWidget{const P({super.key});@override Widget build(c)=>const SizedBox(height:50,child:Placeholder());}\n' > frontend/lib/ads/_probe_ok.dart
bash scripts/firewall-guard.sh frontend/lib/ads/_probe_ok.dart; echo "ok-exit: $?"   # expect 0
# (b) a file naming the real content field must still BLOCK
printf 'final child_name = "x";\n' > frontend/lib/ads/_probe_bad.dart
bash scripts/firewall-guard.sh frontend/lib/ads/_probe_bad.dart; echo "bad-exit: $?" # expect 2
rm -f frontend/lib/ads/_probe_ok.dart frontend/lib/ads/_probe_bad.dart
```
Expected: `ok-exit: 0`, `bad-exit: 2`.

- [ ] **Step 4: Run the isolation test (still green with the current lib/ads)**

Run: `cd frontend && flutter test test/ads/ad_isolation_test.dart`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/firewall-guard.sh frontend/test/ads/ad_isolation_test.dart
git commit -m "chore(firewall): scope the ad-layer child check to child_name (allow Flutter child:)"
```

---

### Task 2: `AdConfig` — test ad-unit id + SDK init (inside `lib/ads/`)

**Files:**
- Modify: `frontend/lib/ads/ad_config.dart`
- Test: `frontend/test/ads/ad_config_test.dart` (new)

**Interfaces:**
- Produces: `AdConfig.bannerAdUnitId` (String, platform-switched test id), `AdConfig.initialize()` (`Future<void>` → `MobileAds.instance.initialize()`), unchanged `AdConfig.nonPersonalizedRequest()`.

- [ ] **Step 1: Write the failing test** — `frontend/test/ads/ad_config_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/ads/ad_config.dart';

void main() {
  test('bannerAdUnitId is a Google test unit (never a real/monetizing id)', () {
    final id = AdConfig.bannerAdUnitId;
    expect(id, isNotEmpty);
    // Google's public test publisher id — guarantees no real serving/revenue.
    expect(id.startsWith('ca-app-pub-3940256099942544/'), true,
        reason: 'must be a Google TEST ad unit, got: $id');
  });

  test('ad requests stay non-personalized (npa=1, D21)', () {
    expect(AdConfig.nonPersonalizedRequest().nonPersonalizedAds, true);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && flutter test test/ads/ad_config_test.dart`
Expected: FAIL — `bannerAdUnitId` is undefined.

- [ ] **Step 3: Implement** — replace `frontend/lib/ads/ad_config.dart` with:

```dart
import 'dart:io' show Platform;

import 'package:google_mobile_ads/google_mobile_ads.dart';

/// Ad layer. FIREWALL (D19): this file must never import app/feature models
/// or reference any user-derived data. Launch ads are non-personalized
/// (npa=1, D21). The prototype serves Google TEST ad units only — no real
/// serving, no revenue, no account.
class AdConfig {
  static AdRequest nonPersonalizedRequest() =>
      const AdRequest(nonPersonalizedAds: true);

  /// Google's public TEST banner unit (per platform). Real ad-unit ids are a
  /// launch-time swap; until then these guarantee test-only serving.
  static String get bannerAdUnitId => Platform.isIOS
      ? 'ca-app-pub-3940256099942544/2934735716'
      : 'ca-app-pub-3940256099942544/6300978111';

  /// Initialize the Mobile Ads SDK. Called only when ads are enabled.
  static Future<void> initialize() => MobileAds.instance.initialize();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && flutter test test/ads/ad_config_test.dart test/ads/ad_isolation_test.dart`
Expected: PASS (isolation test still green — the new code stays SDK-only under `lib/ads/`).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/ads/ad_config.dart frontend/test/ads/ad_config_test.dart
git commit -m "feat(frontend): AdConfig test banner unit id + SDK init (lib/ads only)"
```

---

### Task 3: `adsEnabledProvider` — the flag gate (in `lib/core/`, no SDK import)

**Files:**
- Modify: `frontend/lib/core/providers.dart`
- Test: `frontend/test/core/ads_enabled_provider_test.dart` (new)

**Interfaces:**
- Produces: `const kShowAds` (bool, from `SHOW_ADS` dart-define) and `final adsEnabledProvider` (`Provider<bool>`). Task 5 reads `adsEnabledProvider`; `main.dart` reads `kShowAds`.

- [ ] **Step 1: Write the failing test** — `frontend/test/core/ads_enabled_provider_test.dart`:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/core/providers.dart';

void main() {
  test('adsEnabled defaults to false when SHOW_ADS is unset', () {
    final c = ProviderContainer();
    addTearDown(c.dispose);
    expect(c.read(adsEnabledProvider), false);
  });

  test('adsEnabledProvider is overridable (the test/build seam)', () {
    final c = ProviderContainer(
      overrides: [adsEnabledProvider.overrideWithValue(true)],
    );
    addTearDown(c.dispose);
    expect(c.read(adsEnabledProvider), true);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && flutter test test/core/ads_enabled_provider_test.dart`
Expected: FAIL — `adsEnabledProvider` undefined.

- [ ] **Step 3: Implement** — add to `frontend/lib/core/providers.dart` (after the existing top-level `const` declarations near the top of the file, e.g. below `_iosClientId`):

```dart
// Ad prototype gate (spec 2026-07-17). Off unless the build passes
// --dart-define=SHOW_ADS=true. Kept in core (not lib/ads) so nothing outside
// lib/ads/ imports the ad SDK. Wrapped in a provider so widget tests can flip it.
const kShowAds = bool.fromEnvironment('SHOW_ADS', defaultValue: false);

final adsEnabledProvider = Provider<bool>((ref) => kShowAds);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && flutter test test/core/ads_enabled_provider_test.dart`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/core/providers.dart frontend/test/core/ads_enabled_provider_test.dart
git commit -m "feat(frontend): adsEnabledProvider + SHOW_ADS flag (off by default)"
```

---

### Task 4: `AdBannerSlot` — the fixed-height test banner widget

**Files:**
- Create: `frontend/lib/ads/ad_banner_slot.dart`
- Test: `frontend/test/ads/ad_banner_slot_test.dart` (new)

**Interfaces:**
- Consumes: `AdConfig.bannerAdUnitId`, `AdConfig.nonPersonalizedRequest()` (Task 2).
- Produces: `class AdBannerSlot extends StatefulWidget` — a `const`-constructible widget that always occupies 50 logical px and shows a test banner when loaded, empty otherwise.

- [ ] **Step 1: Write the failing test** — `frontend/test/ads/ad_banner_slot_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/ads/ad_banner_slot.dart';

void main() {
  testWidgets('reserves a fixed 50px slot even when no ad loads (no reflow, no crash)',
      (tester) async {
    // In a unit test the Ads plugin channel is unimplemented, so the banner
    // never fills — the slot must still render its reserved height and never throw.
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: AdBannerSlot())),
    );
    await tester.pump();

    final slot = tester.widget<SizedBox>(
      find.byKey(const Key('ad-banner-slot')),
    );
    expect(slot.height, 50);
    expect(tester.takeException(), isNull);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && flutter test test/ads/ad_banner_slot_test.dart`
Expected: FAIL — `ad_banner_slot.dart` does not exist.

- [ ] **Step 3: Implement** — create `frontend/lib/ads/ad_banner_slot.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:google_mobile_ads/google_mobile_ads.dart';

import 'ad_config.dart';

/// A firewalled test-ad banner (D19: takes no app/user data). Always reserves a
/// fixed height so surrounding content never reflows when the ad fills; if the
/// ad fails or never loads, the reserved area simply stays blank.
class AdBannerSlot extends StatefulWidget {
  const AdBannerSlot({super.key});

  @override
  State<AdBannerSlot> createState() => _AdBannerSlotState();
}

class _AdBannerSlotState extends State<AdBannerSlot> {
  static const double _height = 50;
  BannerAd? _banner;
  bool _loaded = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _load() {
    final banner = BannerAd(
      size: AdSize.banner,
      adUnitId: AdConfig.bannerAdUnitId,
      request: AdConfig.nonPersonalizedRequest(),
      listener: BannerAdListener(
        onAdLoaded: (_) {
          if (mounted) setState(() => _loaded = true);
        },
        // Load failure is non-fatal: dispose and leave the reserved slot blank.
        onAdFailedToLoad: (ad, _) => ad.dispose(),
      ),
    );
    _banner = banner;
    // Best-effort: a missing plugin/channel (e.g. tests) must never throw.
    try {
      banner.load();
    } catch (_) {}
  }

  @override
  void dispose() {
    _banner?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      key: const Key('ad-banner-slot'),
      height: _height,
      child: (_loaded && _banner != null) ? AdWidget(ad: _banner!) : null,
    );
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && flutter test test/ads/`
Expected: PASS (banner-slot test + ad_config test + isolation test — the isolation test auto-covers the new `lib/ads/` file).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/ads/ad_banner_slot.dart frontend/test/ads/ad_banner_slot_test.dart
git commit -m "feat(frontend): AdBannerSlot — fixed-height firewalled test banner"
```

---

### Task 5: Anchor the slot in `HomeShell` + init the SDK in `main`

**Files:**
- Modify: `frontend/lib/ui/home_shell.dart`
- Modify: `frontend/lib/main.dart`
- Test: `frontend/test/ui/ad_anchored_body_test.dart` (new)

**Interfaces:**
- Consumes: `adsEnabledProvider`, `kShowAds` (Task 3); `AdBannerSlot` (Task 4); `AdConfig.initialize()` (Task 2).
- Produces: top-level `Widget adAnchoredBody({required bool showAds, required Widget content})` in `home_shell.dart` — the testable seam that adds the slot below `content`.

- [ ] **Step 1: Write the failing test** — `frontend/test/ui/ad_anchored_body_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/ads/ad_banner_slot.dart';
import 'package:mamaflow/ui/home_shell.dart';

void main() {
  testWidgets('adAnchoredBody omits the ad slot when showAds is false',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: adAnchoredBody(showAds: false, content: const Placeholder()),
      ),
    ));
    expect(find.byType(AdBannerSlot), findsNothing);
    expect(find.byType(Placeholder), findsOneWidget);
  });

  testWidgets('adAnchoredBody includes the ad slot when showAds is true',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: adAnchoredBody(showAds: true, content: const Placeholder()),
      ),
    ));
    await tester.pump();
    expect(find.byType(AdBannerSlot), findsOneWidget);
    expect(find.byType(Placeholder), findsOneWidget);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && flutter test test/ui/ad_anchored_body_test.dart`
Expected: FAIL — `adAnchoredBody` undefined.

- [ ] **Step 3a: Implement `adAnchoredBody` + wire `HomeShell`** — in `frontend/lib/ui/home_shell.dart`, add the import and the helper, and change `build`'s `body:`:

Add imports at the top (with the existing imports):

```dart
import '../ads/ad_banner_slot.dart';
```

Add this top-level function (below the imports, above the `HomeShell` class):

```dart
/// The signed-in shell body with an optional anchored ad slot below the
/// content. Extracted so the flag-conditional is unit-testable without pumping
/// the full screen stack. FIREWALL: passes the slot no content data.
Widget adAnchoredBody({required bool showAds, required Widget content}) {
  return Column(
    children: [
      Expanded(child: content),
      if (showAds) const AdBannerSlot(),
    ],
  );
}
```

In `_HomeShellState.build`, replace the `Scaffold(body: IndexedStack(...), ...)` so the body routes through the helper:

```dart
  @override
  Widget build(BuildContext context) {
    final showAds = ref.watch(adsEnabledProvider);
    return Scaffold(
      body: adAnchoredBody(
        showAds: showAds,
        content: IndexedStack(
          index: _index,
          children: const [HomeScreen(), CalendarScreen()],
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.list_alt), label: 'Agenda'),
          NavigationDestination(icon: Icon(Icons.calendar_month), label: 'Calendar'),
        ],
      ),
    );
  }
```

(`adsEnabledProvider` is already reachable via the existing `import '../core/providers.dart';`.)

- [ ] **Step 3b: Init the SDK in `main` when enabled** — in `frontend/lib/main.dart`, add the import and the guarded init:

Add import:

```dart
import 'ads/ad_config.dart';
import 'core/providers.dart';
```

In `main()`, after the Firebase init block and before `runApp`:

```dart
  // Ad prototype: initialize the Mobile Ads SDK only when explicitly enabled,
  // so a normal build pays zero ad startup cost. Best-effort like Firebase.
  if (kShowAds) {
    try {
      await AdConfig.initialize();
    } catch (_) {}
  }
```

- [ ] **Step 4: Run tests + analyze**

Run: `cd frontend && flutter test test/ui/ad_anchored_body_test.dart && flutter analyze`
Expected: PASS (2 tests); analyze clean. (`main.dart` importing `ad_config.dart` is fine — the isolation test only forbids the string `google_mobile_ads` outside `lib/ads/`, which `main.dart` does not contain.)

- [ ] **Step 5: Run the FULL frontend suite (nothing regressed)**

Run: `cd frontend && flutter test`
Expected: all pass (82 baseline + the new ad tests). Isolation test still green.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/ui/home_shell.dart frontend/lib/main.dart frontend/test/ui/ad_anchored_body_test.dart
git commit -m "feat(frontend): anchor AdBannerSlot in HomeShell; init Ads SDK when SHOW_ADS"
```

---

### Task 6: Decision log + HANDOFF + on-device verification note

**Files:**
- Modify: `DECISIONS.md` (append the next `Dn`)
- Modify: `HANDOFF.md`

**Interfaces:** none.

- [ ] **Step 1: Append a decision to `DECISIONS.md`** (use the next free `Dn`, matching the existing table format):

```
| D<next> | Ad-placement UX prototype moved up before E0 (firewalled AdMob TEST banner, flag-off by default) | locked | Serves Google TEST ad units only — no AdMob account, no revenue, no invalid-traffic risk. Deliberate exception to the "ad layer only after verify" scope boundary for UX/perf validation + tester distribution. D19 (firewall) and D21 (monetization) unchanged. Real ad-unit ids + AdMob account + app-ads.txt + privacy-policy AdMob row are a launch-time swap. Spec: docs/superpowers/specs/2026-07-17-ad-prototype-design.md. |
```

- [ ] **Step 2: Add a HANDOFF note** — append to the most recent update block or add a short one:

```
> **Ad prototype (2026-07-17):** firewalled AdMob TEST banner anchored bottom of the shell,
> gated by --dart-define=SHOW_ADS=true (off by default). Testers see ads working via test
> creatives — no account, no cost, no ban risk. Real serving is a launch-time swap (real ids +
> app-ads.txt at the E0 domain + published app + privacy-policy AdMob row). Build the tester
> distribution WITH the flag; everyday builds omit it and behave as today.
```

- [ ] **Step 3: Verify the flagged build compiles** (the on-device eyeball is the PM's, but confirm it builds with the flag):

Run:
```bash
cd frontend && flutter build apk --debug \
  --dart-define=API_BASE_URL=https://mamaflow-production.up.railway.app \
  --dart-define=GOOGLE_IOS_CLIENT_ID=682580051335-t2pf5pi319mg7cfub2b5725fv907ttq7.apps.googleusercontent.com \
  --dart-define=SHOW_ADS=true
```
Expected: `✓ Built build/app/outputs/flutter-apk/app-debug.apk`.

- [ ] **Step 4: Firewall guard + commit**

```bash
bash scripts/firewall-guard.sh   # expect exit 0 (only the pre-existing gmail_reader WARN)
git add DECISIONS.md HANDOFF.md
git commit -m "docs: ad prototype decision (Dn) + HANDOFF; verified flagged build"
git push
```

---

## Post-plan process gates (SDD, not tasks)

Feature-wide **security-auditor** pass (touches the ad layer — verify the slot references no content, SDK stays under `lib/ads/`, npa=1, flag-off default) and the **final whole-branch review**, per the established per-feature pattern. Then the PM does the on-device eyeball: install the `SHOW_ADS=true` build on the emulator and confirm the test banner sits cleanly above the nav without reflowing the Agenda/Calendar.
