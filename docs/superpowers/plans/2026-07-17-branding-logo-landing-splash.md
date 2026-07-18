# Mamaflow Branding — Logo, Landing/Sign-in & Splash Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Mamaflow a brand identity — a heart-in-a-message-bubble logo — and apply it to the landing/sign-in screen, an in-app splash, the native launch screen, and the launcher icon (iOS + Android).

**Architecture:** The mark is a single pure-vector `CustomPaint` (`AppLogo`). A dev-only Flutter tool renders that same painter to master PNGs, which drive `flutter_launcher_icons` and `flutter_native_splash` — so in-app logo, icon, and splash are pixel-identical and never drift. Everything is presentation/config; no runtime dependency, no data flow, no backend.

**Tech Stack:** Flutter/Dart, `CustomPaint`, `flutter_animate` (already a dep), dev-only generators `flutter_launcher_icons` + `flutter_native_splash`. Tests: `flutter_test` + `mocktail`.

## Global Constraints

- **Brand accent (Mama Coral):** `Color(0xFFF27E63)` — already `AppColors.seed` in `frontend/lib/theme/app_colors.dart`. Use it; never hardcode a second coral literal outside `app_colors.dart` (the painter/generator/configs reference `AppColors.seed` or the hex `#F27E63` in pubspec only).
- **Fonts:** Fredoka for the wordmark/headlines, Nunito for body — already the theme default (`fontFamily: 'Nunito'`; Fredoka via `displayLarge`/`headlineMedium`/`titleLarge`). Use theme text styles, do not hardcode `fontFamily`.
- **Design tokens:** spacing/radii/motion come from `frontend/lib/theme/tokens.dart` (`AppSpacing`, `AppRadii`, `AppDurations`, `AppCurves`) — no inline magic numbers in the screens.
- **THE FIREWALL (D19):** touch only `frontend/lib/ui/`, `frontend/lib/theme/`, `frontend/tool/`, `frontend/assets/`, `frontend/pubspec.yaml`, and native iOS/Android config. Never `lib/ads/` or the `adAnchoredBody` boundary.
- **No new runtime dependency.** `flutter_svg` stays out; the two generators go in `dev_dependencies` only.
- **Sign-in test invariants (verbatim):** the signed-out screen shows exactly one **`Continue with Google`** button (`find.text('Continue with Google')` findsOneWidget), **`Mamaflow`** is findable, and the sign-out→sign-in flow still lands on `Continue with Google` (`frontend/test/app_test.dart`). Keep the error copy **`Sign-in failed. Please try again.`** and the tagline **`Your family calendar, from your inbox.`**
- **Motion must be finite** — every added animation must let `pumpAndSettle()` settle (one-shot, or torn down with the transient state it lives in).
- **Run all commands from `frontend/`.** Tests: `flutter test`. Analyze: `flutter analyze` (must stay clean).

---

### Task 1: `AppLogo` — the heart-in-bubble mark

**Files:**
- Create: `frontend/lib/theme/app_logo.dart`
- Test: `frontend/test/theme/app_logo_test.dart`

**Interfaces:**
- Consumes: `AppColors.seed` (`Color(0xFFF27E63)`) from `frontend/lib/theme/app_colors.dart`.
- Produces:
  - `enum AppLogoStyle { coralOnLight, whiteOnCoral }`
  - `class AppLogo extends StatelessWidget` — `const AppLogo({Key? key, double size = 96, AppLogoStyle style = AppLogoStyle.coralOnLight})`.
  - `class MamaflowLogoPainter extends CustomPainter` — `MamaflowLogoPainter(this.style)`; `final AppLogoStyle style;`.

**Notes on the two styles:**
- `coralOnLight`: coral bubble + **solid white** heart. For in-app on cream surfaces.
- `whiteOnCoral`: **white bubble** with the heart **cleared to transparency** (via `saveLayer` + `BlendMode.clear`), so whatever coral sits behind (splash bg, adaptive-icon bg, an opaque coral square) shows through as the heart. Used only by the asset generator (Task 2).

- [ ] **Step 1: Write the failing test**

```dart
// frontend/test/theme/app_logo_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/theme/app_logo.dart';

void main() {
  testWidgets('AppLogo builds and paints at both styles without throwing',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              AppLogo(size: 96),
              AppLogo(size: 40, style: AppLogoStyle.whiteOnCoral),
            ],
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byType(AppLogo), findsNWidgets(2));
    expect(tester.takeException(), isNull);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/theme/app_logo_test.dart`
Expected: FAIL — `Target of URI doesn't exist: 'package:mamaflow/theme/app_logo.dart'` / `AppLogo` undefined.

- [ ] **Step 3: Write the implementation**

```dart
// frontend/lib/theme/app_logo.dart
import 'package:flutter/material.dart';

import 'app_colors.dart';

/// How the mark is coloured.
enum AppLogoStyle {
  /// Coral bubble + solid white heart — for cream/light surfaces (in-app).
  coralOnLight,

  /// White bubble with the heart cleared to transparency — for a coral
  /// background (splash, adaptive-icon foreground, opaque coral icon square).
  /// Used by the asset generator; the transparent heart lets the coral behind
  /// show through.
  whiteOnCoral,
}

/// The Mamaflow brand mark: a heart inside a rounded message bubble. Pure
/// vector so it stays crisp at any size and doubles as the source for the
/// generated launcher icon + splash (see tool/generate_brand_assets.dart).
class AppLogo extends StatelessWidget {
  const AppLogo({super.key, this.size = 96, this.style = AppLogoStyle.coralOnLight});

  final double size;
  final AppLogoStyle style;

  @override
  Widget build(BuildContext context) => SizedBox(
        width: size,
        height: size,
        child: CustomPaint(painter: MamaflowLogoPainter(style)),
      );
}

class MamaflowLogoPainter extends CustomPainter {
  MamaflowLogoPainter(this.style);

  final AppLogoStyle style;

  static const Color _coral = AppColors.seed;

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.shortestSide;
    final bubble = _bubblePath(s);
    final heart = _heartPath(Rect.fromLTRB(s * 0.26, s * 0.20, s * 0.74, s * 0.60));

    switch (style) {
      case AppLogoStyle.coralOnLight:
        canvas.drawPath(bubble, Paint()..color = _coral..isAntiAlias = true);
        canvas.drawPath(heart, Paint()..color = Colors.white..isAntiAlias = true);
      case AppLogoStyle.whiteOnCoral:
        // Layer so BlendMode.clear only erases within the bubble → the heart
        // becomes real transparency in a captured image.
        canvas.saveLayer(Offset.zero & size, Paint());
        canvas.drawPath(bubble, Paint()..color = Colors.white..isAntiAlias = true);
        canvas.drawPath(heart, Paint()..blendMode = BlendMode.clear..isAntiAlias = true);
        canvas.restore();
    }
  }

  /// Rounded "message bubble" squircle with a small rounded tail at lower-left.
  Path _bubblePath(double s) {
    final rect = Rect.fromLTRB(s * 0.10, s * 0.08, s * 0.90, s * 0.78);
    final body = Path()
      ..addRRect(RRect.fromRectAndRadius(rect, Radius.circular(s * 0.24)));
    final tail = Path()
      ..moveTo(s * 0.30, s * 0.72)
      ..lineTo(s * 0.20, s * 0.92)
      ..lineTo(s * 0.46, s * 0.74)
      ..close();
    return Path.combine(PathOperation.union, body, tail);
  }

  /// A symmetric heart mapped into [r] (normalised cubic-bezier control points,
  /// y-down). Kept inside [0,1] so it never spills the bubble.
  Path _heartPath(Rect r) {
    Offset n(double nx, double ny) =>
        Offset(r.left + nx * r.width, r.top + ny * r.height);
    return Path()
      ..moveTo(n(0.50, 0.28).dx, n(0.50, 0.28).dy)
      ..cubicTo(n(0.50, 0.13).dx, n(0.50, 0.13).dy, n(0.72, 0.05).dx,
          n(0.72, 0.05).dy, n(0.85, 0.18).dx, n(0.85, 0.18).dy)
      ..cubicTo(n(0.98, 0.31).dx, n(0.98, 0.31).dy, n(0.93, 0.55).dx,
          n(0.93, 0.55).dy, n(0.50, 0.85).dx, n(0.50, 0.85).dy)
      ..cubicTo(n(0.07, 0.55).dx, n(0.07, 0.55).dy, n(0.02, 0.31).dx,
          n(0.02, 0.31).dy, n(0.15, 0.18).dx, n(0.15, 0.18).dy)
      ..cubicTo(n(0.28, 0.05).dx, n(0.28, 0.05).dy, n(0.50, 0.13).dx,
          n(0.50, 0.13).dy, n(0.50, 0.28).dx, n(0.50, 0.28).dy)
      ..close();
  }

  @override
  bool shouldRepaint(MamaflowLogoPainter oldDelegate) => oldDelegate.style != style;
}
```

- [ ] **Step 4: Run test + analyze**

Run: `flutter test test/theme/app_logo_test.dart && flutter analyze`
Expected: PASS; analyze clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/theme/app_logo.dart frontend/test/theme/app_logo_test.dart
git commit -m "feat(frontend): AppLogo heart-in-bubble brand mark (vector CustomPaint)"
```

---

### Task 2: Brand asset generator → master PNGs

**Files:**
- Create: `frontend/tool/generate_brand_assets.dart`
- Create (generated + committed): `frontend/assets/brand/icon_1024.png`, `frontend/assets/brand/icon_foreground_1024.png`, `frontend/assets/brand/splash_logo_1024.png`
- Modify: `frontend/pubspec.yaml` (register `assets/brand/` under `flutter: assets:`)

**Interfaces:**
- Consumes: `AppLogo`, `AppLogoStyle` (Task 1); `AppColors.seed`.
- Produces: the three committed PNGs consumed by Tasks 5 & 6.

**Why a widget test:** the Flutter test binding can rasterize a `RepaintBoundary` via `toImage()`. Rendering the *same* painter guarantees the icon/splash match the in-app logo. It lives in `tool/` (not `test/`) so `flutter test` (no args) never runs it — it writes files and is a manual dev step.

- [ ] **Step 1: Register the asset dir in `pubspec.yaml`**

Under the existing `flutter:` → `assets:` list (create the list if absent), add:

```yaml
    assets:
      - assets/brand/
```

- [ ] **Step 2: Write the generator**

```dart
// frontend/tool/generate_brand_assets.dart
//
// Dev tool (NOT part of the CI test run — lives in tool/, not test/).
// Regenerate the brand PNGs from the AppLogo vector:
//   cd frontend && flutter test tool/generate_brand_assets.dart
//
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/theme/app_colors.dart';
import 'package:mamaflow/theme/app_logo.dart';

Future<void> _capture(
  WidgetTester tester,
  String path, {
  required double logoSize,
  Color? background, // null => transparent
}) async {
  final key = GlobalKey();
  await tester.pumpWidget(Directionality(
    textDirection: TextDirection.ltr,
    child: RepaintBoundary(
      key: key,
      child: Container(
        width: 1024,
        height: 1024,
        color: background,
        alignment: Alignment.center,
        child: AppLogo(size: logoSize, style: AppLogoStyle.whiteOnCoral),
      ),
    ),
  ));
  await tester.pumpAndSettle();

  final boundary = key.currentContext!.findRenderObject() as RenderRepaintBoundary;
  final ui.Image image = (await tester.runAsync(() => boundary.toImage(pixelRatio: 1.0)))!;
  final ByteData bytes =
      (await tester.runAsync(() => image.toByteData(format: ui.ImageByteFormat.png)))!;
  final file = File(path);
  file.parent.createSync(recursive: true);
  file.writeAsBytesSync(bytes.buffer.asUint8List());
}

void main() {
  testWidgets('generate brand assets', (tester) async {
    // Exact 1024x1024 capture surface.
    await tester.binding.setSurfaceSize(const Size(1024, 1024));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    // Opaque icon: coral square + white bubble (heart shows coral through).
    await _capture(tester, 'assets/brand/icon_1024.png',
        logoSize: 760, background: AppColors.seed);
    // Adaptive foreground: white bubble on transparent, inside the ~66% safe
    // zone so the launcher mask can't clip it (620/1024 ≈ 0.61).
    await _capture(tester, 'assets/brand/icon_foreground_1024.png',
        logoSize: 620, background: null);
    // Splash logo: white bubble on transparent (sits on the coral splash bg).
    await _capture(tester, 'assets/brand/splash_logo_1024.png',
        logoSize: 560, background: null);

    for (final p in const [
      'assets/brand/icon_1024.png',
      'assets/brand/icon_foreground_1024.png',
      'assets/brand/splash_logo_1024.png',
    ]) {
      final f = File(p);
      expect(f.existsSync(), isTrue, reason: '$p not written');
      expect(f.lengthSync(), greaterThan(1000), reason: '$p suspiciously small');
    }
  });
}
```

- [ ] **Step 3: Run the generator**

Run: `flutter test tool/generate_brand_assets.dart`
Expected: PASS; the three PNGs appear under `frontend/assets/brand/`.

- [ ] **Step 4: Eyeball the PNGs (manual)**

Open `frontend/assets/brand/icon_1024.png` — a coral rounded square with a white message bubble and a coral heart cutout. `splash_logo_1024.png` and `icon_foreground_1024.png` — the same white bubble with a transparent heart, on a checkerboard (transparent) background. If the heart is filled white instead of transparent, `whiteOnCoral`'s `saveLayer`/`BlendMode.clear` regressed — fix Task 1 before continuing.

- [ ] **Step 5: Confirm `flutter test` (no args) still green + analyze**

Run: `flutter test && flutter analyze`
Expected: the full suite passes (the generator in `tool/` is not picked up); analyze clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/tool/generate_brand_assets.dart frontend/assets/brand/ frontend/pubspec.yaml
git commit -m "feat(frontend): brand asset generator (AppLogo -> master PNGs)"
```

---

### Task 3: Landing / sign-in redesign

**Files:**
- Modify: `frontend/lib/ui/sign_in_screen.dart` (full presentation rewrite; sign-in logic unchanged)
- Test: `frontend/test/ui/sign_in_screen_test.dart` (new)

**Interfaces:**
- Consumes: `AppLogo` (Task 1); `sessionProvider` (`frontend/lib/auth/session_controller.dart`) — the existing `signIn()` flow, unchanged; `AppSpacing`/`AppRadii` from tokens.
- Produces: nothing new (screen is a leaf).

- [ ] **Step 1: Write the failing test**

```dart
// frontend/test/ui/sign_in_screen_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/theme/app_logo.dart';
import 'package:mamaflow/ui/sign_in_screen.dart';

void main() {
  testWidgets('renders the brand, tagline, trust lines and CTA', (tester) async {
    await tester.pumpWidget(const ProviderScope(
      child: MaterialApp(home: SignInScreen()),
    ));
    await tester.pumpAndSettle();

    expect(find.byType(AppLogo), findsOneWidget);
    expect(find.text('Mamaflow'), findsOneWidget);
    expect(find.text('Your family calendar, from your inbox.'), findsOneWidget);
    expect(find.textContaining('never used for ads'), findsOneWidget);
    // NB: use find.text, not widgetWithText(FilledButton, …) — FilledButton.icon
    // has a private runtime type that find.byType(FilledButton) won't match.
    expect(find.text('Continue with Google'), findsOneWidget);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/ui/sign_in_screen_test.dart`
Expected: FAIL — the current screen has no `AppLogo` and no trust line, so the `find.byType(AppLogo)` and `find.textContaining('never used for ads')` expectations fail (the `Continue with Google` / `Mamaflow` / tagline expectations already pass).

- [ ] **Step 3: Rewrite the screen**

```dart
// frontend/lib/ui/sign_in_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/session_controller.dart';
import '../theme/app_logo.dart';
import '../theme/tokens.dart';

/// Shown when no session JWT is present. The single action runs the mobile
/// Google sign-in -> backend exchange -> JWT store flow (logic unchanged).
class SignInScreen extends ConsumerStatefulWidget {
  const SignInScreen({super.key});

  @override
  ConsumerState<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends ConsumerState<SignInScreen> {
  bool _busy = false;
  String? _error;

  Future<void> _signIn() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(sessionProvider.notifier).signIn();
      // On success the auth gate swaps to the home screen automatically.
    } catch (e) {
      // Debug-only diagnostic: error type + message (never tokens/PII).
      debugPrint('sign-in failed: ${e.runtimeType}: $e');
      if (mounted) setState(() => _error = 'Sign-in failed. Please try again.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(AppSpacing.xl),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const AppLogo(size: 104)
                    .animate()
                    .fadeIn(duration: AppDurations.slow)
                    .scale(begin: const Offset(0.8, 0.8), curve: AppCurves.standard),
                const SizedBox(height: AppSpacing.lg),
                Text('Mamaflow', style: text.displaySmall),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  'Your family calendar, from your inbox.',
                  style: text.bodyLarge?.copyWith(color: scheme.onSurfaceVariant),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: AppSpacing.xl),
                const _TrustLine(
                    icon: Icons.mark_email_read_outlined,
                    text: 'Turns your inbox into a family calendar'),
                const SizedBox(height: AppSpacing.md),
                const _TrustLine(
                    icon: Icons.lock_outline,
                    text: 'Private by design — your email is never used for ads'),
                const SizedBox(height: AppSpacing.md),
                const _TrustLine(
                    icon: Icons.auto_awesome_outlined,
                    text: 'Free, with an ad-free option'),
                const SizedBox(height: AppSpacing.xl),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: _busy ? null : _signIn,
                    icon: _busy
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.login),
                    label: const Text('Continue with Google'),
                  ),
                ),
                if (_error != null) ...[
                  const SizedBox(height: AppSpacing.lg),
                  Text(_error!,
                      style: text.bodyMedium?.copyWith(color: scheme.error),
                      textAlign: TextAlign.center),
                ],
                const SizedBox(height: AppSpacing.xl),
                Text(
                  'We only read your email to find family events. Nothing is shared.',
                  style: text.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _TrustLine extends StatelessWidget {
  const _TrustLine({required this.icon, required this.text});
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final style = Theme.of(context).textTheme;
    return Row(
      children: [
        Icon(icon, size: 20, color: scheme.primary),
        const SizedBox(width: AppSpacing.md),
        Expanded(child: Text(text, style: style.bodyMedium)),
      ],
    );
  }
}
```

- [ ] **Step 4: Run the new test, the app test, and analyze**

Run: `flutter test test/ui/sign_in_screen_test.dart test/app_test.dart && flutter analyze`
Expected: PASS (both the new test and the existing `app_test` sign-in invariants); analyze clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/ui/sign_in_screen.dart frontend/test/ui/sign_in_screen_test.dart
git commit -m "feat(frontend): branded landing/sign-in (logo, wordmark, trust lines, CTA)"
```

---

### Task 4: In-app splash (AuthGate hydrate)

**Files:**
- Create: `frontend/lib/ui/widgets/brand_splash.dart`
- Modify: `frontend/lib/app.dart` (replace the `AuthGate` `loading:` spinner)

**Interfaces:**
- Consumes: `AppLogo` (Task 1); `AppDurations`/`AppCurves` tokens.
- Produces: `class BrandSplash extends StatelessWidget` — `const BrandSplash()`.

**Motion:** a **one-shot** fade + gentle scale (finite — `pumpAndSettle`-safe). Do NOT use an infinite repeat.

- [ ] **Step 1: Write the failing test**

```dart
// frontend/test/ui/brand_splash_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/theme/app_logo.dart';
import 'package:mamaflow/ui/widgets/brand_splash.dart';

void main() {
  testWidgets('BrandSplash shows the logo and settles', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: BrandSplash()));
    await tester.pumpAndSettle(); // must settle: animation is one-shot
    expect(find.byType(AppLogo), findsOneWidget);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/ui/brand_splash_test.dart`
Expected: FAIL — `BrandSplash` undefined.

- [ ] **Step 3: Implement `BrandSplash`**

```dart
// frontend/lib/ui/widgets/brand_splash.dart
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

import '../../theme/app_logo.dart';
import '../../theme/tokens.dart';

/// The in-app splash shown while the session hydrates (AuthGate loading). Warm
/// cream surface + the brand mark with a one-shot fade/scale entrance. Kept
/// finite so pumpAndSettle settles once hydrate completes and this is removed.
class BrandSplash extends StatelessWidget {
  const BrandSplash({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: const AppLogo(size: 96)
            .animate()
            .fadeIn(duration: AppDurations.slow)
            .scale(begin: const Offset(0.85, 0.85), curve: AppCurves.standard),
      ),
    );
  }
}
```

- [ ] **Step 4: Wire it into `AuthGate`**

In `frontend/lib/app.dart`, add the import and replace the loading branch.

Add near the other `ui/` imports:
```dart
import 'ui/widgets/brand_splash.dart';
```

Replace:
```dart
      loading: () => const Scaffold(body: Center(child: CircularProgressIndicator())),
```
with:
```dart
      loading: () => const BrandSplash(),
```

- [ ] **Step 5: Run tests + analyze**

Run: `flutter test test/ui/brand_splash_test.dart test/app_test.dart && flutter analyze`
Expected: PASS; analyze clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/ui/widgets/brand_splash.dart frontend/lib/app.dart frontend/test/ui/brand_splash_test.dart
git commit -m "feat(frontend): branded in-app splash on session hydrate"
```

---

### Task 5: Launcher icon (flutter_launcher_icons)

**Files:**
- Modify: `frontend/pubspec.yaml` (dev dep + `flutter_launcher_icons:` config)
- Regenerated + committed: `frontend/ios/Runner/Assets.xcassets/AppIcon.appiconset/*`, `frontend/android/app/src/main/res/mipmap-*/*`, `frontend/android/app/src/main/res/mipmap-anydpi-v26/*`, `frontend/android/app/src/main/res/values/colors.xml` (adaptive bg)

**Interfaces:**
- Consumes: `assets/brand/icon_1024.png`, `assets/brand/icon_foreground_1024.png` (Task 2).

- [ ] **Step 1: Add the dev dependency + config to `pubspec.yaml`**

Under `dev_dependencies:` add:
```yaml
  flutter_launcher_icons: ^0.14.4
```
At top level (sibling of `flutter:`), add:
```yaml
flutter_launcher_icons:
  android: true
  ios: true
  image_path: "assets/brand/icon_1024.png"
  remove_alpha_ios: true
  min_sdk_android: 21
  adaptive_icon_background: "#F27E63"
  adaptive_icon_foreground: "assets/brand/icon_foreground_1024.png"
```

- [ ] **Step 2: Fetch deps**

Run: `flutter pub get`
Expected: resolves (if `^0.14.4` is unavailable, use the latest `flutter_launcher_icons` the resolver accepts and note the version in the commit).

- [ ] **Step 3: Generate the icons**

Run: `dart run flutter_launcher_icons`
Expected: "✓ Successfully generated launcher icons" — iOS `AppIcon.appiconset` + Android mipmaps + adaptive XML rewritten.

- [ ] **Step 4: Verify + analyze**

Run: `flutter analyze`
Expected: clean. Confirm `git status` shows changed files under `ios/Runner/Assets.xcassets/AppIcon.appiconset/` and `android/app/src/main/res/mipmap-*`. Open one generated `mipmap-xxxhdpi/ic_launcher.png` — coral square + white bubble.

- [ ] **Step 5: Commit**

```bash
git add frontend/pubspec.yaml frontend/pubspec.lock frontend/ios/Runner/Assets.xcassets/AppIcon.appiconset frontend/android/app/src/main/res
git commit -m "feat(frontend): branded launcher icon (iOS + Android adaptive) via flutter_launcher_icons"
```

---

### Task 6: Native splash screen (flutter_native_splash)

**Files:**
- Modify: `frontend/pubspec.yaml` (dev dep + `flutter_native_splash:` config)
- Regenerated + committed: `frontend/ios/Runner/Base.lproj/LaunchScreen.storyboard`, `frontend/ios/Runner/Assets.xcassets/LaunchImage.imageset/*`, `frontend/android/app/src/main/res/drawable*/launch_background.xml`, `frontend/android/app/src/main/res/values*/styles.xml`, `frontend/android/app/src/main/res/drawable*/` splash images, `frontend/android/app/src/main/res/values*/colors.xml`

**Interfaces:**
- Consumes: `assets/brand/splash_logo_1024.png` (Task 2).

- [ ] **Step 1: Add the dev dependency + config to `pubspec.yaml`**

Under `dev_dependencies:` add:
```yaml
  flutter_native_splash: ^2.4.4
```
At top level, add:
```yaml
flutter_native_splash:
  color: "#F27E63"
  image: "assets/brand/splash_logo_1024.png"
  android: true
  ios: true
  android_12:
    color: "#F27E63"
    image: "assets/brand/splash_logo_1024.png"
```

- [ ] **Step 2: Fetch deps**

Run: `flutter pub get`
Expected: resolves (if `^2.4.4` is unavailable, use the latest the resolver accepts; note the version in the commit).

- [ ] **Step 3: Generate the native splash**

Run: `dart run flutter_native_splash:create`
Expected: "✓ Native splash complete" — iOS storyboard + Android launch backgrounds/styles rewritten to coral + logo.

- [ ] **Step 4: Verify + analyze + full suite**

Run: `flutter analyze && flutter test`
Expected: analyze clean; all tests green (splash config is native-only, no Dart test impact). Confirm `android/app/src/main/res/drawable/launch_background.xml` now references the coral color + splash image, and `ios/Runner/Base.lproj/LaunchScreen.storyboard` references the new splash image.

- [ ] **Step 5: Commit**

```bash
git add frontend/pubspec.yaml frontend/pubspec.lock frontend/ios/Runner frontend/android/app/src/main/res
git commit -m "feat(frontend): branded native splash (coral + logo, iOS + Android 12) via flutter_native_splash"
```

---

### Task 7: Docs — HANDOFF + DECISIONS

**Files:**
- Modify: `HANDOFF.md` (new update block)
- Modify: `DECISIONS.md` (append D33)

- [ ] **Step 1: Append the decision to `DECISIONS.md`**

Add as the next entry (verify the number — use the next `Dn` after the last one in the file; shown here as D33):

```markdown
### D33 — Brand identity: heart-in-a-message-bubble, "Mama Coral" (2026-07-17)
Mamaflow's mark is a heart inside a rounded message bubble (inbox → family/care), in Mama Coral
(#F27E63) with the Fredoka wordmark. Implemented as a single pure-vector `AppLogo` CustomPaint;
a dev-only Flutter tool (`tool/generate_brand_assets.dart`) renders that painter to master PNGs
that drive `flutter_launcher_icons` + `flutter_native_splash` (dev-only deps) — one source of
truth for in-app logo, launcher icon, and splash. No new runtime dependency; firewall untouched.
```

- [ ] **Step 2: Add a HANDOFF update block**

Add after the most recent update block in `HANDOFF.md`:

```markdown
> **Update 2026-07-17 — Branding: logo + landing/sign-in + splash + launcher icon.** Plan
> `docs/superpowers/plans/2026-07-17-branding-logo-landing-splash.md`, spec
> `docs/superpowers/specs/2026-07-17-branding-logo-landing-splash-design.md`. The heart-in-bubble
> `AppLogo` (vector) now brands: the redesigned sign-in/landing (logo + Fredoka wordmark + three
> trust lines + in-button loading), an in-app hydrate splash (`BrandSplash`), the native launch
> screen (coral + logo, iOS + Android 12), and the launcher icon (iOS + Android adaptive) — killing
> the default Flutter icon/splash before the tester distribution. Master PNGs are generated from the
> same painter (`tool/generate_brand_assets.dart`) so nothing drifts. Presentation/config only;
> firewall untouched; sign-in test invariants preserved. **USER: rebuild on device to see the new
> icon/splash** (native assets only appear on a fresh install/run).
```

- [ ] **Step 3: Commit**

```bash
git add HANDOFF.md DECISIONS.md
git commit -m "docs: record branding (D33) + HANDOFF update"
```

---

## Verification (end-to-end)

- After each task: `cd frontend && flutter test` green; `flutter analyze` clean.
- Task 2 is a manual generator run (`flutter test tool/generate_brand_assets.dart`) — eyeball the PNGs.
- Tasks 5 & 6 run the generators and commit native output; confirm `git status` shows the regenerated iOS/Android files.
- Final: `flutter run -d <device> --dart-define=API_BASE_URL=… --dart-define=GOOGLE_IOS_CLIENT_ID=…` and eyeball: the coral native splash on cold start → the in-app `BrandSplash` during hydrate → the branded sign-in screen; background the app to see the new launcher icon. `bash scripts/firewall-guard.sh` exit 0.

## Out of scope (documented fast-follow)

Dark theme for landing/splash; animated/Lottie splash; Google-guidelines-exact sign-in button chrome; App Store / marketing assets. All still-gated ad/monetization work stays on E0.
