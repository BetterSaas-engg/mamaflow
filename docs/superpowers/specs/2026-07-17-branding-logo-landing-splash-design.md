# Mamaflow Branding — Logo, Landing/Sign-in & Splash (Design)

**Date:** 2026-07-17
**Status:** Approved (PM), ready for implementation plan.
**Context:** Fast-follow deferred from the UI redesign plan (`docs/superpowers/plans/2026-07-17-ui-redesign.md`,
"Out of scope: app launcher icon/branding rebrand"). The warm redesign shipped (Mama Coral #F27E63,
Nunito/Fredoka), but the **front door has no brand**: the sign-in screen is a bare bold-text + generic
button, the splash is the **default Flutter white screen + placeholder logo**, and the launcher icon is
the **default Flutter icon**. This spec adds a brand mark and applies it across the landing/sign-in
screen, an in-app splash, the native launch screen, and the launcher icon.

## Decided direction (PM, 2026-07-17)

- **Logo motif:** a **heart inside a rounded message bubble** — the inbox/message (bubble) carrying
  family & care (heart). Coral field, white heart, small bubble tail. Friendly, rounded, legible small.
- **Scope:** **full rebrand** — in-app landing/sign-in redesign + branded in-app splash + real launcher
  icon (iOS + Android) + native launch screen (iOS + Android incl. Android 12+ splash API).
- **Style:** consistent with the shipped redesign — Mama Coral `#F27E63`, Fredoka wordmark, Nunito body,
  warm cream surfaces, tasteful one-shot motion.

## Guardrails (non-negotiable)

- **THE FIREWALL (D19):** this work lives only in `frontend/lib/ui/`, `frontend/lib/theme/`, native
  iOS/Android config, and `assets/`. It does **not** touch `lib/ads/` or the `adAnchoredBody` boundary.
- **No new runtime dependency.** The mark is a pure-vector Flutter `CustomPaint`; `flutter_svg` stays
  out. The two new packages (`flutter_launcher_icons`, `flutter_native_splash`) are **dev-only**
  generators (`dev_dependencies`), not shipped code.
- **Tests stay green + `flutter analyze` clean.** Preserve the sign-in test invariants (see §6).

---

## 1. The logo mark — `AppLogo` (single source of truth)

### 1.1 Artwork
A rounded-square "message bubble" with a **heart** centered inside and a short tail at the bottom-left
(the classic chat-bubble notch). Proportions: bubble ≈ a squircle (superellipse-ish rounded rect) with
corner radius ≈ 28% of side; heart ≈ 46% of the bubble's inner width, optically centered slightly high;
tail ≈ a small rounded triangle merging from the bubble's lower-left. All strokeless (filled shapes).

### 1.2 Two treatments (one painter, parameterized)
- **`AppLogoStyle.coralOnLight`** — coral bubble (`#F27E63`) + white heart. Used in-app on cream
  surfaces (sign-in hero, in-app splash).
- **`AppLogoStyle.whiteOnCoral`** — **white bubble with the heart as a transparent cutout** (the coral
  behind shows through as the heart). One definition, used everywhere a coral background sits behind the
  mark: the native splash logo, the Android adaptive-icon foreground, and the iOS icon square. On the
  cream in-app surface this style is not used (there's no coral behind), so the cutout is never a
  problem. In `CustomPaint`/in-app rendering the "cutout" is drawn as a coral-colored heart on the white
  bubble; in the exported PNGs the heart is genuine transparency so the platform's coral background/field
  becomes the heart.

`AppLogo({double size, AppLogoStyle style})` is a `StatelessWidget` wrapping a `CustomPaint` with a
`MamaflowLogoPainter`. No animation inside `AppLogo` itself — callers add motion (keeps it reusable for
the static icon export).

### 1.3 Raster generation — render the widget to PNG (no external image tools)
A dev tool renders the **same** `MamaflowLogoPainter` to master PNGs via `RepaintBoundary.toImage()` so
the in-app logo, launcher icon, and splash are pixel-identical artwork:

- Tool: `frontend/tool/generate_brand_assets.dart` run as a Flutter **widget test** (test binding
  supports `boundary.toImage()` under `tester.runAsync`). It paints the logo at 1024×1024 and writes
  (all from the same `whiteOnCoral` painter so every surface matches):
  - `assets/brand/icon_1024.png` — **opaque**: a full coral square + the white bubble (heart cutout
    showing coral), mark centered with padding. iOS icons must have no alpha, so the coral fills the
    square (this doubles as the Android legacy/round icon source).
  - `assets/brand/icon_foreground_1024.png` — the white bubble (heart = transparent cutout) on a
    **transparent** ground, within the Android adaptive safe zone (mark inside the inner ~66% so the
    launcher mask can't clip it); the adaptive **background** is the flat coral color, which fills the
    heart cutout and the field.
  - `assets/brand/splash_logo_1024.png` — the white bubble (heart = transparent cutout) on
    **transparent**, sitting on the coral splash background.
- These PNGs are committed (reproducible: re-run the tool to regenerate).

*Alternative considered & rejected:* hand-authoring a separate PNG (Pillow/SVG) — risks in-app-vs-icon
drift and adds tooling for no gain.

**Files:** create `frontend/lib/theme/app_logo.dart` (`AppLogo`, `AppLogoStyle`, `MamaflowLogoPainter`),
`frontend/tool/generate_brand_assets.dart`, `frontend/assets/brand/*.png`; modify `pubspec.yaml`
(assets + dev deps + generator configs).

## 2. Landing / sign-in redesign (`lib/ui/sign_in_screen.dart`)

Presentation-only rewrite of the existing screen; the sign-in **logic is unchanged** (`_signIn()` →
`sessionProvider.notifier.signIn()` → AuthGate swaps to home). Warm cream `Scaffold`, centered column,
`SafeArea`, generous spacing from `AppSpacing`:

- **Hero:** `AppLogo(style: coralOnLight)` (~96–112px) with a **one-shot** entrance (fade + gentle
  scale/float via `flutter_animate`); the **`Mamaflow`** wordmark in Fredoka (`displaySmall`/
  `headlineMedium`); tagline *"Your family calendar, from your inbox."* in `onSurfaceVariant`.
- **Three trust points** — a small column of `icon + text` rows, wedge first:
  1. `Icons.mark_email_read_outlined` — "Turns your inbox into a family calendar"
  2. `Icons.lock_outline` — "Private by design — your email is never used for ads"
  3. `Icons.auto_awesome_outlined` — "Free, with an ad-free option"
- **Primary CTA:** the **`Continue with Google`** button (exact label — test invariant), coral
  `FilledButton`, pill, full-width-ish. While `_busy`: the button shows an in-button spinner and is
  disabled (replaces the current bare centered `CircularProgressIndicator`).
- **Error:** inline `Text` in `Theme.of(context).colorScheme.error` (not `Colors.red`), copy unchanged
  ("Sign-in failed. Please try again.").
- **Footer:** one soft privacy line, e.g. "We only read your email to find family events. Nothing is
  shared." (No legal links — the privacy-policy URL is gated on E0, matching the settings screen.)

## 3. Splash — native + in-app

### 3.1 Native launch screen (`flutter_native_splash`)
Coral (`#F27E63`) background + centered white logo (`assets/brand/splash_logo_1024.png`). Config in
`pubspec.yaml` (`flutter_native_splash:` block): `color: "#F27E63"`, `image: assets/brand/...`,
`android_12:` block (coral `color` + `image` for the Android 12+ splash API), `ios: true`. Run
`dart run flutter_native_splash:create`; commit the regenerated iOS `LaunchScreen.storyboard` +
`Assets.xcassets` and Android `drawable*/launch_background.xml` + `values*/styles.xml` + splash drawables.

### 3.2 In-app splash (`lib/app.dart` `AuthGate`)
Replace the bare `CircularProgressIndicator` in `AuthGate`'s `loading:` branch with a small branded
widget: `AppLogo(style: coralOnLight)` centered on the cream surface with a **subtle, transient** pulse
(scale/opacity). It is short-lived (session hydrate) like the spinner it replaces; the animation must be
`pumpAndSettle`-safe (either a finite one-shot, or a repeat that is torn down when hydrate completes —
same class as the `CircularProgressIndicator`/`LoadingState` already in use). New widget:
`frontend/lib/ui/widgets/brand_splash.dart` (or inline in `app.dart` if trivial).

### 3.3 Launcher icon (`flutter_launcher_icons`)
Config in `pubspec.yaml` (`flutter_launcher_icons:` block): `image_path: assets/brand/icon_1024.png`;
Android adaptive — `adaptive_icon_background: "#F27E63"`, `adaptive_icon_foreground:
assets/brand/icon_foreground_1024.png`; iOS from the opaque `icon_1024.png` (`remove_alpha_ios: true`).
Run `dart run flutter_launcher_icons`; commit regenerated `AppIcon.appiconset` + Android mipmaps/adaptive
XML.

## 4. Architecture & data flow

- **Isolation:** `AppLogo`/painter is a leaf widget with no dependencies beyond `AppColors` — usable by
  sign-in, in-app splash, and the asset generator. The generator is a build-time tool, not shipped.
- **No data flow / no network / no persistence / no secrets** introduced anywhere. Sign-in reuses the
  existing session flow verbatim.
- **Native regeneration** is deterministic from the committed PNGs + config; a fresh clone can rebuild
  identical native assets by re-running the two generators.

## 5. Error handling

- Sign-in errors: unchanged behavior, restyled to `colorScheme.error`.
- `Firebase.initializeApp()` / native splash removal: unaffected (native splash auto-dismisses on first
  Flutter frame; the in-app splash then covers hydrate).
- Missing/failed asset: the app still functions (logo is a widget; a missing raster only affects the
  generated native icon/splash, which are committed artifacts).

## 6. Testing

- **Preserve invariants** (`test/app_test.dart`): sign-in shows exactly one **`Continue with Google`**;
  **`Mamaflow`** still findable; the signed-out→in→out flow still works (sign-out returns to the sign-in
  screen with `Continue with Google`).
- **New:** a smoke test that `AppLogo` builds and paints without throwing at a couple of sizes/styles
  (`tester.pumpWidget` + `expect(find.byType(AppLogo), findsOneWidget)`), and that the sign-in screen
  renders the wordmark + tagline + the three trust lines + the button.
- **Motion:** the sign-in entrance and the in-app splash animations must be finite / torn-down so
  `pumpAndSettle()` settles (no looping hang).
- **Asset generator** is a manually-run dev tool (not part of the CI test run gate); note in the plan
  that it's run once to (re)produce the PNGs.
- `flutter analyze` clean.

## 7. Out of scope (documented)

- Dark theme for the landing/splash (light-only, consistent with the app).
- Animated/Lottie splash, marketing website, App Store assets.
- Google-brand-exact sign-in button chrome (we keep a clean coral button with the required label; a
  Google-guidelines button is a later polish if needed).
- Any monetization / real-ad work (still gated on E0).

## 8. Critical files

- Create: `frontend/lib/theme/app_logo.dart`, `frontend/tool/generate_brand_assets.dart`,
  `frontend/assets/brand/{icon_1024,icon_foreground_1024,splash_logo_1024}.png`,
  `frontend/lib/ui/widgets/brand_splash.dart`.
- Modify: `frontend/lib/ui/sign_in_screen.dart`, `frontend/lib/app.dart` (AuthGate loading),
  `frontend/pubspec.yaml` (assets, dev deps, `flutter_launcher_icons` + `flutter_native_splash` configs).
- Regenerated (committed): iOS `Runner/Assets.xcassets/AppIcon.appiconset`,
  `Runner/Base.lproj/LaunchScreen.storyboard`, Android `res/mipmap*`, `res/drawable*/launch_background.xml`,
  `res/values*/styles.xml`, adaptive-icon XML + splash drawables.
- Tests: `frontend/test/ui/sign_in_screen_test.dart` (new), existing `frontend/test/app_test.dart`
  (must stay green).
