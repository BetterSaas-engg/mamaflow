# Mamaflow UI Redesign — Warm & Friendly (Mama Coral)

## Context

Mamaflow's engine is done and proven (Gmail → extraction → calendar/todos, hourly auto-sync, evening
reminders, durable tokens, a firewalled ad prototype). But the **UI is a blank-slate default**: the
Flutter app ships pure Material 3 baseline-purple with **no theme, no design tokens, no custom fonts,
no brand identity** — `MaterialApp.router` (`lib/app.dart:34`) passes only `title` + `routerConfig`, and
styling is ~30 inline `Colors.grey`/`Colors.red`/`TextStyle`/`EdgeInsets` literals across 6 screen files.
Before distributing to testers and moving toward launch, the app needs a cohesive, beautiful, interactive
look that matches the product's promise: a caring, trustworthy helper for busy parents. This plan
establishes a design system and redesigns the two screens users live in.

## Decided direction (PM, 2026-07-17)

- **Aesthetic:** Warm & friendly. **Brand accent = "Mama Coral" `#F27E63`** (soft terracotta-coral).
- **Approach:** Hybrid — grounded in family-calendar patterns (Cozi/Fantastical/Structured), built as a
  cohesive Material 3 design system + redesigned screens.
- **Scope (core first):** design-system foundation applied app-wide via `ThemeData`, plus full redesign of
  **Agenda** (home) and **Calendar** and the shared components they use. Sign-in / item-detail / settings
  inherit the theme immediately; a per-screen polish pass on them + dark theme is a documented fast-follow.
- **Motion:** Tasteful polish — page transitions, staggered list entrance, animated chips, illustrated
  empty state, done/dismiss haptics. Alive, not distracting.

## Guardrails (non-negotiable)

- **THE FIREWALL (D19):** do not touch `lib/ads/` or the `adAnchoredBody` boundary; the ad banner keeps
  its fixed 50px reserved slot below content and receives no app/user data. Presentation-only redesign.
- **Logic untouched:** reuse `lib/items/grouping.dart`, `lib/*/filters.dart`, `lib/calendar/*`, and the
  Riverpod providers (`itemsProvider`, `calendarItemsProvider`, `items_controller.dart`) as-is.
- **Tests stay green** (see §6 — the redesign must preserve every find-by-text assertion) and
  `flutter analyze` must stay clean.

---

## 1. Design system foundation — new `lib/theme/`

**`app_colors.dart`** — `ColorScheme.fromSeed(seedColor: Color(0xFFF27E63), brightness: light)`, then
`.copyWith` warm surface overrides so backgrounds read as cream, not M3 cool-white:
`surface #FFFBF7`, `surfaceContainerLowest #FFFFFF`, `surfaceContainerLow #FFF6F0`,
`surfaceContainer #FDEFE8`, `surfaceContainerHigh #FAE7DD` (leave primary/containers as generated coral).
Semantic getters replace inline literals: muted text → `onSurfaceVariant` (every `Colors.grey`),
destructive → `error` (every `Colors.red`).

**`category_colors.dart`** — `Color categoryColor(String? eventType)` + `IconData categoryIcon(...)`.
Normalized substring match: medical/health/doctor/dentist → `#E5737B` rose (`medical_services_outlined`);
sports/soccer/practice/swim → `#5FA97E` green (`sports_soccer`); school/class/exam → `#5B8DEF` blue
(`school_outlined`); birthday/party → `#F2A65A` amber; **unknown → deterministic pick from an 8-color warm
palette by `eventType.hashCode`** (stable color for any novel type). Actions (no eventType) →
`check_circle_outline`.

**`tokens.dart`** — replace all magic numbers: `AppSpacing{hair2,xs4,sm8,md12,lg16,xl24,xxl32}`,
`AppRadii{sm8,md12,lg16,xl20,pill999}`, `AppShadows.card = BoxShadow(0x14000000, blur16, offset(0,4))`,
`AppDurations{fast150,medium250,slow400}`, `AppCurves{standard: easeOutCubic}`.

**Typography — add `google_fonts`, run offline/deterministic** (`GoogleFonts.config.allowRuntimeFetching
= false` in `main.dart`, bundle the TTFs in `assets/fonts/` + pubspec `fonts:`): body/UI **Nunito**
(`GoogleFonts.nunitoTextTheme`), headlines/wordmark **Fredoka**. Matches the soft-rounded warm brief and
the privacy positioning (no runtime network fetch).

**`app_theme.dart`** — `buildLightTheme()` = `ThemeData(useMaterial3, colorScheme, textTheme, …)` with
component themes so every call site inherits the redesign: `cardTheme` (elevation 0, radius lg, warm
surface, `AppShadows`), `chipTheme` (pill, selected=primaryContainer), `appBarTheme`
(surface, `scrolledUnderElevation:0`, Fredoka title), `navigationBarTheme` (coral indicator, labels
shown), `floatingActionButtonTheme` (coral pill), `filledButtonTheme`, `snackBarTheme`, `dividerTheme`,
`listTileTheme`, and a **`pageTransitionsTheme`** (fade + slide-up) that upgrades every existing
`MaterialPageRoute` push app-wide with zero navigation-code changes. Include a `buildDarkTheme()` stub
(same builder, `Brightness.dark`) but ship **light-only** now (`themeMode: ThemeMode.light`).

**Wire** in `app.dart:34`: `theme: buildLightTheme()`, `themeMode: ThemeMode.light`.

## 2. Shared components — new `lib/ui/widgets/`

Promote the private per-screen widgets into a reusable set:

- **`ItemCard`** (the hub, replaces `_ItemTile` in home_screen and `_DayItemTile` in calendar) — warm
  rounded card: leading circular badge tinted `categoryColor(...).withValues(alpha:.16)` holding
  `categoryIcon(...)`; title in Nunito w600 (strikethrough + muted when `status` done/dismissed —
  preserves current closed-state semantics); a meta row of small pill chips (`date·time`, `eventType`,
  `childName` — same fields the current `subtitleParts` builds); trailing **`PopupMenuButton<String>`**
  with **`Mark done`/`Dismiss`** when open (labels/type unchanged — a test depends on them), or a status
  `Chip` when closed; `onTap` → `ItemDetailScreen` (unchanged). Params `dense`, `showDate` (calendar
  hides the redundant date).
- **`FilterChipBar`** (replaces `_chips`) — keeps real **`FilterChip`** widgets fed by
  `childValues`/`typeValues`, single-select child-XOR-type logic unchanged; restyled + animated selection.
- **`SectionHeader`** (replaces `_header`) — muted uppercase label + optional count pill; **titles still
  come from `grouping.dart` unchanged**.
- **`EmptyState`** — friendly illustration via **`CustomPaint` + icon composition (no `flutter_svg`)**: a
  soft coral circle backdrop + composed calendar/heart glyph; `EmptyState(title, message, action?)`.
  Agenda copy keeps the substring **"No items"** (a test uses `textContaining('No items')`).
- **`LoadingState`** — skeleton of 4–5 pulsing card placeholders (hand-rolled `AnimatedBuilder`, no
  shimmer dep), replacing the bare spinner.
- **`ErrorState`** (from `_Centered`) — icon + message + `Retry` (contract preserved).
- **`SyncProgressCard`** (from `_SyncProgressCard`) — same `SyncStatus` data, warm card + rounded
  `LinearProgressIndicator`.
- Nav bar / FAB / app bar need no new widget — handled by component themes.

## 3. Agenda + Calendar redesign

**Agenda (`home_screen.dart`)** — presentation only; reuses `applyChipFilter → groupItems → sections`.
Keep `Text('Mamaflow')` (Fredoka), the show-completed `IconButton`, the Settings `IconButton`
(`tooltip:'Settings'`), and the `Icons.sync` + `'Sync inbox'` FAB. `CustomScrollView`: `FilterChipBar`
sliver, then per group a `SectionHeader` + `SliverList` of `ItemCard`s spaced by `AppSpacing.sm` (cards,
not `Divider`s), `AppSpacing.lg` horizontal padding. Empty → `EmptyState`; loading → `LoadingState`;
error → `ErrorState`.

**Calendar (`calendar_screen.dart`)** — reuses `calendarItemsProvider`, `itemsByDate`, `monthGrid`. Keep
the month/year title, prev/next `IconButton`s, `Today`. Restyle `_WeekdayHeader` (muted Nunito). Restyle
`_DayCell` (`AnimatedContainer`, radius md): **today** = coral ring on the number; **selected** = soft
`primaryContainer` fill; **items** = up to 3 small **category-colored dots** (by `eventType`) replacing
the single primary dot — keep `Text('$day')` + tap handler intact. Selected-day list → `ItemCard(dense:
true, showDate: false)` with a "Tuesday, July 14"-style date header; empty → inline `EmptyState`.

## 4. Motion — tasteful polish (add `flutter_animate`)

- **Page transitions:** via `pageTransitionsTheme` (fade + slide-up) — upgrades item-detail/settings
  pushes app-wide, no navigation code changed.
- **Staggered entrance:** `ItemCard`s `.animate(delay: index*40ms).fadeIn(250).slideY(begin:.08)`,
  **one-shot only** (gate so scroll/rebuild doesn't re-trigger), capped per section.
- **Chips:** subtle `AnimatedScale`/scale pop on selection (stays a `FilterChip`).
- **Done/dismiss:** wrap `ItemCard` in `Dismissible` (swipe → `setStatus`, same logic) with
  `HapticFeedback.mediumImpact()` and an animated removal; the `PopupMenuButton` path stays intact
  alongside it (existing tap test still passes).
- **All animations finite** (entrances one-shot) — `pumpAndSettle()` must still settle (see §6).

## 5. New dependencies (pure UI — no backend/firewall impact)

- `google_fonts` — Nunito/Fredoka `textTheme`, run with `allowRuntimeFetching=false` + bundled TTFs.
- `flutter_animate` — staggered entrances, chip/empty-state polish, done/dismiss removal.
- **Not** adding `flutter_svg` (illustrations are `CustomPaint`). Add `assets/fonts/` TTFs to pubspec.
  None touch `lib/ads/`, `lib/core/`, or the backend.

## 6. Test invariants the redesign MUST preserve (verified against the suite)

- Section headers exact: **`Later`**, **`To-do — no date`** (`items/home_screen_test`).
- Chips are **`FilterChip`** with labels **`Emma`/`Charlie`** (`widgetWithText(FilterChip, …)`).
- Agenda empty contains **`No items`** (`textContaining`).
- Open item keeps **`PopupMenuButton<String>`** + **`Mark done`** (tapped by test).
- Calendar day cells render **`Text('$day')`**, tappable; tapped day shows **`Soccer`**.
- Nav labels **`Agenda`/`Calendar`**; calendar month/year title.
- **`Mamaflow`**, **`byTooltip('Settings')`**, `Sign out`, `Continue with Google`, `Delete account`
  (+ its `FilledButton`/`TextField`), `Open source email`, item-detail field texts (`Emma`), `Mark done`.
- `adAnchoredBody` still toggles `AdBannerSlot` on `showAds` — don't change that function's structure.
- **Animation gotcha:** every added animation must be finite; a looping animation hangs `pumpAndSettle`.

## 7. Task breakdown (dependency order, each independently testable)

1. **Deps + assets:** add `google_fonts`, `flutter_animate`, `assets/fonts/` TTFs + `fonts:`; `flutter pub get`.
2. **Tokens** (`tokens.dart`).
3. **Colors** (`app_colors.dart` + `category_colors.dart`).
4. **Theme** (`app_theme.dart`: light theme + component themes + `pageTransitionsTheme`; dark stub).
5. **Wire** `app.dart` + `main.dart` (fonts offline). **Run full suite** — proves theme-only change breaks nothing.
6. **`SectionHeader`**.
7. **`ItemCard`** (replace `_ItemTile`; keep popup menu + labels + onTap). Run `home_screen_test`.
8. **`FilterChipBar`** (replace `_chips`; keep `FilterChip`). Run `home_screen_test`.
9. **`EmptyState`/`ErrorState`/`LoadingState`/`SyncProgressCard`**.
10. **Agenda redesign** (`home_screen.dart` → shared components). Run `home_screen_test`.
11. **Calendar redesign** (`_DayCell` category dots + today/selected `AnimatedContainer`; `ItemCard(dense)`
    day list; date header; `_WeekdayHeader`/`Today`). Run `calendar_screen_test` + `home_shell_test`.
12. **Motion** (staggered one-shot, chip pop, `Dismissible` + haptics + removal; page transitions).
    **Run full suite** (confirm `pumpAndSettle` settles).
13. **Polish/docs:** `flutter analyze` clean; note the documented fast-follow (per-screen polish for
    sign-in/item-detail/settings — which already inherit the theme — plus dark theme).

**Execution:** subagent-driven development (fresh implementer per task + per-task review gate + final
whole-branch review), consistent with this session's other features. Firewall guard runs on every edit.

## Verification (end-to-end)

- After each task: `cd frontend && flutter test` green; `flutter analyze` clean.
- Steps 5/7/8/10/11/12 specifically re-run the named widget tests (they guard find-by-text).
- Final: `flutter run -d emulator-5554 --dart-define=API_BASE_URL=… --dart-define=GOOGLE_IOS_CLIENT_ID=…`
  and eyeball Agenda + Calendar — coral theme, category colors/dots, staggered entrance, swipe
  done/dismiss + haptics, page transitions; confirm the ad slot (`--dart-define=SHOW_ADS=true`) still lays
  out correctly below content. `bash scripts/firewall-guard.sh` exit 0.

## Critical files

- `lib/app.dart` (theme wiring) · `lib/main.dart` (fonts offline)
- `lib/ui/home_screen.dart` (Agenda; source of `_ItemTile`/`_chips`/`_header`/`_Centered`/`_SyncProgressCard`)
- `lib/ui/calendar_screen.dart` (Calendar; `_DayCell`/`_DayItemTile`/`_WeekdayHeader`)
- `pubspec.yaml` (deps + fonts/assets)
- New: `lib/theme/{app_theme,app_colors,category_colors,tokens}.dart`, `lib/ui/widgets/{item_card,
  filter_chip_bar,section_header,empty_state,loading_state,error_state,sync_progress_card}.dart`

## Out of scope (documented fast-follow)

Per-screen polish for sign-in / item-detail / settings (they inherit the new theme now, but get bespoke
layouts later), dark theme, app launcher icon/branding rebrand, and any real-ad/monetization work.
