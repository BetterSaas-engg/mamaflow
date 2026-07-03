# Flutter Frontend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Flutter app foundation (project + core units: api_client, auth, push, isolated ads, app shell) plus the decision-log/tooling changes the platform switch requires — without the screen-by-screen UI.

**Architecture:** A Flutter mobile app in `frontend/` (polyglot monorepo with the Python `backend/`). Thin REST/JSON client to FastAPI; Riverpod for state, go_router for routing. Four isolated units with clear interfaces; the `ads` unit is structurally walled off from any content/event/child data (the firewall, expressed in code). Backend endpoints are owned by the backend team (see `docs/backend-requirements-from-frontend.md`); this plan builds the app against that contract and unit-tests with mocks.

**Tech Stack:** Flutter (Dart), Riverpod, go_router, dio, flutter_secure_storage, firebase_messaging + flutter_local_notifications, google_sign_in, google_mobile_ads. Tests: flutter_test + mocktail.

## Global Constraints

- **Firewall (D19):** no content/event/child data — or anything derived from it — may reach the `ads` unit. The `ads` unit imports nothing from `features/*` or item models.
- **Privacy (D4):** OAuth/Gmail tokens never on device or in the DB beyond server-side secret storage. The app stores ONLY its own session JWT (in `flutter_secure_storage`).
- **Privacy (D5):** raw email bodies never stored anywhere.
- **Monetization (D21):** launch ads are AdMob **non-personalized (`npa=1`)**.
- **Platform:** Flutter mobile-first (iOS + Android); web later (Flutter Web, deferred).
- **Decision log:** this work flips D9/D20 → Flutter and adds D22 (FCM push), D23 (mobile Google OAuth).
- **Commits:** Conventional Commits; small; the git pre-commit firewall guard must stay green.

## Prerequisites & blockers (read before executing)

- **Phase 0** (tooling/docs) needs nothing extra — runnable now.
- **Phase 1** (Flutter app) needs the **Flutter SDK** installed (`flutter --version`); for device/sim builds also **full Xcode** (iOS) and **Android SDK/Studio**. Unit tests (`flutter test`) only need the Flutter SDK.
- **Phase 2** (platform integration) additionally needs: a **Firebase project** + **APNs key** (iOS push), **iOS/Android OAuth client IDs** in GCP, an **AdMob account/app id**, and the **backend endpoints** from the hand-off note implemented. These tasks are verified on device/emulator, not by unit tests.

---

## Phase 0 — Decision log + tooling (no Flutter required)

### Task 1: Flip the frontend decision in the decision log + AGENTS.md

**Files:**
- Modify: `DECISIONS.md`
- Modify: `AGENTS.md`

**Interfaces:** none (docs).

- [ ] **Step 1: Edit `DECISIONS.md`** — change the D9 and D20 rows' Status from `**under review**` to `locked`, and set their Decision/Notes to Flutter. Replace the D9 row's Notes with: `Frontend = Flutter (mobile-first; web later via Flutter Web). Chosen over PWA+Capacitor/Expo because push is core at launch and the team is productive in Flutter; AdMob is first-class. See docs/superpowers/specs/2026-06-22-frontend-platform-flutter-design.md.` Set D20 Notes to `Superseded — native app via Flutter; App Store/Play distribution required for push.`

- [ ] **Step 2: Append D22 and D23 rows** to the `DECISIONS.md` table:

```markdown
| D22 | Push notifications via Firebase Cloud Messaging (FCM) for both platforms | locked | iOS via an APNs key in Firebase. Backend sends with the FCM HTTP v1 API. |
| D23 | Mobile auth = Google sign-in serverAuthCode → backend token exchange | locked | Gmail tokens stay server-side (D4); app holds only its session JWT. |
```

- [ ] **Step 3: Update the "Open: frontend platform" section** in `DECISIONS.md` — replace its body with one line: `Resolved 2026-06-22: Flutter (see D9/D22/D23 and the design spec).`

- [ ] **Step 4: Edit `AGENTS.md`** — replace the frontend stack line (`- Frontend: React + Vite + Tailwind, thin API consumer. **Delivery platform is under review**...`) with: `- Frontend: **Flutter** (Dart), mobile-first iOS + Android; web later via Flutter Web. Thin REST/JSON consumer of the API. See DECISIONS.md (D9/D22/D23).`

- [ ] **Step 5: Verify** no stale "under review" remains for the platform.

Run: `grep -n "under review" DECISIONS.md AGENTS.md`
Expected: no lines mentioning the frontend platform as under review.

- [ ] **Step 6: Commit**

```bash
git add DECISIONS.md AGENTS.md
git commit -m "docs: lock frontend platform = Flutter (D9/D20 → Flutter; add D22 FCM, D23 mobile OAuth)"
```

### Task 2: Teach the firewall guard about Dart ad files

**Files:**
- Modify: `scripts/firewall-guard.sh` (the ad-layer `case` in HARD BLOCK #3)

**Interfaces:**
- Produces: the guard BLOCKs any Dart file in the ad layer that references event/child/content identifiers.

- [ ] **Step 1: Write the failing test (fixture)** — create a Dart file that should be blocked and run the guard.

```bash
mkdir -p frontend/lib/ads
printf 'class BannerAd {\n  final String childName;\n  BannerAd(this.event);\n}\n' > frontend/lib/ads/leaky_ad.dart
bash scripts/firewall-guard.sh frontend/lib/ads/leaky_ad.dart; echo "EXIT=$?"
```

Expected BEFORE the fix: `EXIT=0` (the file path matches `*ads/*` so it is *already* caught by the existing pattern — confirm this; if it already BLOCKs, the existing `*ads/*` glob covers dir-based ad files and Step 3 only adds filename-based coverage). Document the actual observed exit code.

- [ ] **Step 2: Add Dart filename patterns** to the ad-layer `case` in `scripts/firewall-guard.sh` so ad files NOT under an `ads/` dir are also covered. Change the case label:

```sh
    *ad/*|*ads/*|*advert*|*Ad.tsx|*Ads.tsx|*ad_*.py|*_ads.py|*_ad.dart|*ad_*.dart|*Ad.dart|*_ads.dart)
```

- [ ] **Step 3: Verify a filename-based Dart ad file is blocked**

```bash
printf 'class X { final event; }\n' > frontend/banner_ad.dart
bash scripts/firewall-guard.sh frontend/banner_ad.dart; echo "EXIT=$?"
```
Expected: `EXIT=2` with a `BLOCK ... references content/event/child data` line.

- [ ] **Step 4: Clean up the fixtures**

```bash
rm -f frontend/lib/ads/leaky_ad.dart frontend/banner_ad.dart
rmdir frontend/lib/ads 2>/dev/null || true
```

- [ ] **Step 5: Commit**

```bash
git add scripts/firewall-guard.sh
git commit -m "chore: firewall guard catches Dart ad-layer files referencing content"
```

### Task 3: Add Flutter ignores to .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Append a Flutter section** to `.gitignore`:

```gitignore
# Flutter / Dart (frontend)
frontend/.dart_tool/
frontend/.flutter-plugins
frontend/.flutter-plugins-dependencies
frontend/build/
frontend/.pub-cache/
frontend/.pub/
frontend/ios/Pods/
frontend/ios/.symlinks/
frontend/**/GeneratedPluginRegistrant.*
# Firebase / platform config = treat as secrets, never commit
frontend/**/google-services.json
frontend/**/GoogleService-Info.plist
frontend/android/key.properties
frontend/**/*.keystore
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore Flutter build artifacts + platform secret configs"
```

---

## Phase 1 — Flutter app foundation (requires Flutter SDK)

> Blocker: `flutter --version` must succeed. Install Flutter + run `flutter doctor` first. Unit tests need only the SDK.

### Task 4: Scaffold the Flutter project + pin dependencies

**Files:**
- Create: `frontend/` (Flutter project), `frontend/pubspec.yaml`

**Interfaces:**
- Produces: a buildable Flutter app; `flutter test` runs.

- [ ] **Step 1: Create the project**

```bash
cd /Users/sabiranthapa/Desktop/mamaflow
flutter create --org com.bettersaas.mamaflow --platforms=ios,android frontend
```

- [ ] **Step 2: Add dependencies**

```bash
cd frontend
flutter pub add flutter_riverpod go_router dio flutter_secure_storage \
  firebase_core firebase_messaging flutter_local_notifications \
  google_sign_in google_mobile_ads
flutter pub add --dev mocktail
```

- [ ] **Step 3: Verify the default test passes**

Run: `cd frontend && flutter test`
Expected: PASS (the generated widget test).

- [ ] **Step 4: Commit**

```bash
git add frontend
git commit -m "feat(frontend): scaffold Flutter app + pin foundation dependencies"
```

### Task 5: `api_client` — typed REST client with auth interceptor

**Files:**
- Create: `frontend/lib/core/api_client.dart`
- Test: `frontend/test/core/api_client_test.dart`

**Interfaces:**
- Consumes: a `TokenStore` with `Future<String?> readJwt()` (defined in Task 6 — for the test, inject a fake).
- Produces: `class ApiClient { ApiClient(Dio dio, {required Future<String?> Function() jwtProvider}); Future<Map<String,dynamic>> getJson(String path, {Map<String,dynamic>? query}); Future<Map<String,dynamic>> postJson(String path, Map<String,dynamic> body); }` — attaches `Authorization: Bearer <jwt>` when a JWT is present.

- [ ] **Step 1: Write the failing test**

```dart
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/core/api_client.dart';

class _CapturingAdapter implements HttpClientAdapter {
  RequestOptions? last;
  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<List<int>>? s, Future? cancel) async {
    last = options;
    return ResponseBody.fromString('{"ok":true}', 200,
        headers: {Headers.contentTypeHeader: [Headers.jsonContentType]});
  }
  @override
  void close({bool force = false}) {}
}

void main() {
  test('attaches bearer token when jwt present', () async {
    final dio = Dio(BaseOptions(baseUrl: 'https://api.test'));
    final adapter = _CapturingAdapter();
    dio.httpClientAdapter = adapter;
    final client = ApiClient(dio, jwtProvider: () async => 'TESTJWT');

    final body = await client.getJson('/api/v1/items');

    expect(body['ok'], true);
    expect(adapter.last!.headers['Authorization'], 'Bearer TESTJWT');
  });

  test('omits auth header when no jwt', () async {
    final dio = Dio(BaseOptions(baseUrl: 'https://api.test'));
    final adapter = _CapturingAdapter();
    dio.httpClientAdapter = adapter;
    final client = ApiClient(dio, jwtProvider: () async => null);

    await client.getJson('/api/v1/items');

    expect(adapter.last!.headers.containsKey('Authorization'), false);
  });
}
```

- [ ] **Step 2: Run it — expect failure**

Run: `cd frontend && flutter test test/core/api_client_test.dart`
Expected: FAIL (no `api_client.dart`).

- [ ] **Step 3: Implement `api_client.dart`**

```dart
import 'package:dio/dio.dart';

class ApiClient {
  final Dio _dio;
  final Future<String?> Function() _jwtProvider;

  ApiClient(this._dio, {required Future<String?> Function() jwtProvider})
      : _jwtProvider = jwtProvider {
    _dio.interceptors.add(InterceptorsWrapper(onRequest: (options, handler) async {
      final jwt = await _jwtProvider();
      if (jwt != null && jwt.isNotEmpty) {
        options.headers['Authorization'] = 'Bearer $jwt';
      }
      handler.next(options);
    }));
  }

  Future<Map<String, dynamic>> getJson(String path, {Map<String, dynamic>? query}) async {
    final r = await _dio.get(path, queryParameters: query);
    return Map<String, dynamic>.from(r.data as Map);
  }

  Future<Map<String, dynamic>> postJson(String path, Map<String, dynamic> body) async {
    final r = await _dio.post(path, data: body);
    return Map<String, dynamic>.from(r.data as Map);
  }
}
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd frontend && flutter test test/core/api_client_test.dart`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/core/api_client.dart frontend/test/core/api_client_test.dart
git commit -m "feat(frontend): api_client with bearer-token interceptor"
```

### Task 6: `auth` — session JWT store (D4: only the app's own JWT)

**Files:**
- Create: `frontend/lib/auth/token_store.dart`
- Test: `frontend/test/auth/token_store_test.dart`

**Interfaces:**
- Produces: `class TokenStore { TokenStore(FlutterSecureStorage storage); Future<void> saveJwt(String jwt); Future<String?> readJwt(); Future<void> clear(); }` — wraps secure storage; key `mamaflow_session_jwt`. (This `readJwt` is the `jwtProvider` for Task 5.)

- [ ] **Step 1: Write the failing test** (inject an in-memory fake of the storage interface)

```dart
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/auth/token_store.dart';

class _FakeStorage implements FlutterSecureStorage {
  final Map<String, String> _m = {};
  @override
  Future<void> write({required String key, required String? value,
      IOSOptions? iOptions, AndroidOptions? aOptions, LinuxOptions? lOptions,
      WebOptions? webOptions, MacOsOptions? mOptions, WindowsOptions? wOptions}) async {
    if (value == null) { _m.remove(key); } else { _m[key] = value; }
  }
  @override
  Future<String?> read({required String key, IOSOptions? iOptions, AndroidOptions? aOptions,
      LinuxOptions? lOptions, WebOptions? webOptions, MacOsOptions? mOptions,
      WindowsOptions? wOptions}) async => _m[key];
  @override
  Future<void> delete({required String key, IOSOptions? iOptions, AndroidOptions? aOptions,
      LinuxOptions? lOptions, WebOptions? webOptions, MacOsOptions? mOptions,
      WindowsOptions? wOptions}) async => _m.remove(key);
  @override
  noSuchMethod(Invocation i) => super.noSuchMethod(i);
}

void main() {
  test('saves, reads, clears the session jwt', () async {
    final store = TokenStore(_FakeStorage());
    expect(await store.readJwt(), isNull);
    await store.saveJwt('JWT123');
    expect(await store.readJwt(), 'JWT123');
    await store.clear();
    expect(await store.readJwt(), isNull);
  });
}
```

- [ ] **Step 2: Run it — expect failure**

Run: `cd frontend && flutter test test/auth/token_store_test.dart`
Expected: FAIL (no `token_store.dart`).

- [ ] **Step 3: Implement `token_store.dart`**

```dart
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class TokenStore {
  static const _key = 'mamaflow_session_jwt';
  final FlutterSecureStorage _storage;
  TokenStore(this._storage);

  Future<void> saveJwt(String jwt) => _storage.write(key: _key, value: jwt);
  Future<String?> readJwt() => _storage.read(key: _key);
  Future<void> clear() => _storage.delete(key: _key);
}
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd frontend && flutter test test/auth/token_store_test.dart`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/auth/token_store.dart frontend/test/auth/token_store_test.dart
git commit -m "feat(frontend): secure session-JWT store (tokens stay server-side, D4)"
```

### Task 7: `ads` — isolated AdMob wrapper (firewall in code)

**Files:**
- Create: `frontend/lib/ads/ad_config.dart`
- Test: `frontend/test/ads/ad_isolation_test.dart`

**Interfaces:**
- Produces: `class AdConfig { static AdRequest nonPersonalizedRequest(); }` — builds an AdMob request with `nonPersonalizedAds: true` (`npa=1`, D21). The `ads` library imports ONLY `google_mobile_ads` — no app models.

- [ ] **Step 1: Write the failing test** — assert npa + structural isolation (no forbidden imports in the ads source).

```dart
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_mobile_ads/google_mobile_ads.dart';
import 'package:mamaflow/ads/ad_config.dart';

void main() {
  test('ad requests are non-personalized (npa=1)', () {
    final req = AdConfig.nonPersonalizedRequest();
    expect(req.nonPersonalizedAds, true);
  });

  test('ads source imports nothing from features or item models (firewall)', () {
    final src = File('lib/ads/ad_config.dart').readAsStringSync();
    expect(src.contains("package:mamaflow/features"), false);
    expect(src.contains("family_event"), false);
    expect(RegExp(r'\b(event|child|extraction|email)\b').hasMatch(src), false);
  });
}
```

- [ ] **Step 2: Run it — expect failure**

Run: `cd frontend && flutter test test/ads/ad_isolation_test.dart`
Expected: FAIL (no `ad_config.dart`).

- [ ] **Step 3: Implement `ad_config.dart`**

```dart
import 'package:google_mobile_ads/google_mobile_ads.dart';

/// Ad layer. FIREWALL (D19): this file must never import app/feature models
/// or reference user content. Launch ads are non-personalized (npa=1, D21).
class AdConfig {
  static AdRequest nonPersonalizedRequest() =>
      const AdRequest(nonPersonalizedAds: true);
}
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd frontend && flutter test test/ads/ad_isolation_test.dart`
Expected: PASS.

- [ ] **Step 5: Confirm the deterministic guard also covers it**

```bash
cd /Users/sabiranthapa/Desktop/mamaflow
bash scripts/firewall-guard.sh frontend/lib/ads/ad_config.dart; echo "EXIT=$?"
```
Expected: `EXIT=0` (clean — no forbidden identifiers).

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/ads/ad_config.dart frontend/test/ads/ad_isolation_test.dart
git commit -m "feat(frontend): isolated non-personalized AdMob config (firewall, D19/D21)"
```

### Task 8: `push` — FCM token registration call

**Files:**
- Create: `frontend/lib/push/device_registrar.dart`
- Test: `frontend/test/push/device_registrar_test.dart`

**Interfaces:**
- Consumes: `ApiClient.postJson` (Task 5).
- Produces: `class DeviceRegistrar { DeviceRegistrar(ApiClient api); Future<void> register({required String fcmToken, required String platform}); }` — POSTs `{fcm_token, platform}` to `/api/v1/devices/register` (contract item #4).

- [ ] **Step 1: Write the failing test** (fake ApiClient via mocktail)

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mamaflow/core/api_client.dart';
import 'package:mamaflow/push/device_registrar.dart';

class _MockApi extends Mock implements ApiClient {}

void main() {
  test('registers device token with the backend', () async {
    final api = _MockApi();
    when(() => api.postJson(any(), any())).thenAnswer((_) async => {'ok': true});
    final registrar = DeviceRegistrar(api);

    await registrar.register(fcmToken: 'FCMTOKEN', platform: 'ios');

    verify(() => api.postJson('/api/v1/devices/register',
        {'fcm_token': 'FCMTOKEN', 'platform': 'ios'})).called(1);
  });
}
```

- [ ] **Step 2: Run it — expect failure**

Run: `cd frontend && flutter test test/push/device_registrar_test.dart`
Expected: FAIL (no `device_registrar.dart`).

- [ ] **Step 3: Implement `device_registrar.dart`**

```dart
import '../core/api_client.dart';

class DeviceRegistrar {
  final ApiClient _api;
  DeviceRegistrar(this._api);

  Future<void> register({required String fcmToken, required String platform}) {
    return _api.postJson('/api/v1/devices/register',
        {'fcm_token': fcmToken, 'platform': platform});
  }
}
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd frontend && flutter test test/push/device_registrar_test.dart`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/push/device_registrar.dart frontend/test/push/device_registrar_test.dart
git commit -m "feat(frontend): device-token registration call for push"
```

### Task 9: App shell — Riverpod + go_router + placeholder home

**Files:**
- Create: `frontend/lib/app.dart`, `frontend/lib/core/providers.dart`
- Modify: `frontend/lib/main.dart`
- Test: `frontend/test/app_test.dart`

**Interfaces:**
- Consumes: `ApiClient`, `TokenStore`.
- Produces: `MamaflowApp` widget wrapped in `ProviderScope`; go_router with a `/` route showing a placeholder `HomeScreen` (text "Mamaflow"). Riverpod providers: `tokenStoreProvider`, `apiClientProvider` (wires `TokenStore.readJwt` as `jwtProvider`).

- [ ] **Step 1: Write the failing widget test**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/app.dart';

void main() {
  testWidgets('app boots to the Mamaflow home placeholder', (tester) async {
    await tester.pumpWidget(const MamaflowApp());
    await tester.pumpAndSettle();
    expect(find.text('Mamaflow'), findsOneWidget);
  });
}
```

- [ ] **Step 2: Run it — expect failure**

Run: `cd frontend && flutter test test/app_test.dart`
Expected: FAIL (no `app.dart`).

- [ ] **Step 3: Implement providers, app shell, and main**

`frontend/lib/core/providers.dart`:
```dart
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../auth/token_store.dart';
import 'api_client.dart';

const _baseUrl = String.fromEnvironment('API_BASE_URL', defaultValue: 'http://localhost:8000');

final tokenStoreProvider = Provider<TokenStore>((ref) => TokenStore(const FlutterSecureStorage()));

final apiClientProvider = Provider<ApiClient>((ref) {
  final store = ref.watch(tokenStoreProvider);
  return ApiClient(Dio(BaseOptions(baseUrl: _baseUrl)), jwtProvider: store.readJwt);
});
```

`frontend/lib/app.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class MamaflowApp extends StatelessWidget {
  const MamaflowApp({super.key});
  @override
  Widget build(BuildContext context) => const ProviderScope(child: _Router());
}

class _Router extends StatelessWidget {
  const _Router();
  @override
  Widget build(BuildContext context) {
    final router = GoRouter(routes: [
      GoRoute(path: '/', builder: (_, __) => const HomeScreen()),
    ]);
    return MaterialApp.router(routerConfig: router, title: 'Mamaflow');
  }
}

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});
  @override
  Widget build(BuildContext context) =>
      const Scaffold(body: Center(child: Text('Mamaflow')));
}
```

`frontend/lib/main.dart`:
```dart
import 'package:flutter/material.dart';
import 'app.dart';

void main() => runApp(const MamaflowApp());
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd frontend && flutter test`
Expected: PASS (all unit + widget tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib frontend/test/app_test.dart
git commit -m "feat(frontend): app shell with Riverpod + go_router + placeholder home"
```

---

## Phase 2 — Platform integration (requires accounts + backend; verified on device)

> These need a Firebase project, APNs key, iOS/Android OAuth client IDs, an AdMob app id, and the backend endpoints from `docs/backend-requirements-from-frontend.md`. They are verified by running on a simulator/device, not by unit tests. Do them once the prerequisites exist; keep each a separate commit.

### Task 10: Firebase + FCM wiring
- Add the Firebase apps (iOS/Android), drop `GoogleService-Info.plist` / `google-services.json` (gitignored), init `firebase_core`, request notification permission, fetch the FCM token, and call `DeviceRegistrar.register`. Upload the APNs key to Firebase for iOS. **Verify:** token prints + a test push from the Firebase console arrives on a device.

### Task 11: Mobile Google sign-in → backend exchange
- Configure iOS/Android OAuth client IDs in GCP. Use `google_sign_in` to obtain a serverAuthCode (`gmail.readonly`, offline), POST to `/api/v1/auth/google/mobile`, store the returned JWT via `TokenStore`. **Verify:** sign-in returns a JWT and an authenticated `GET /api/v1/items` succeeds (needs backend items #2/#3).

### Task 12: AdMob app id + a test banner
- Add the AdMob app id to `Info.plist` / `AndroidManifest.xml`, render one banner using `AdConfig.nonPersonalizedRequest()` on a non-content screen. **Verify:** a Google test ad shows; confirm no event/child data is passed into the ad widget.

---

## Self-review (done by author)

- **Spec coverage:** platform decision (Task 1) ✓; module boundaries api_client/auth/push/ads/app-shell (Tasks 5–9) ✓; auth flow (Task 11) ✓; FCM (Tasks 8,10) ✓; ads firewall (Tasks 2,7) ✓; backend direction (hand-off note, referenced) ✓; tooling/gitignore (Tasks 2,3) ✓; testing (each task) ✓. UI screens intentionally deferred (out of scope per spec).
- **Placeholders:** none — every code step has complete code.
- **Type consistency:** `TokenStore.readJwt` feeds `ApiClient.jwtProvider` (Tasks 5/6/9); `ApiClient.postJson` used by `DeviceRegistrar` (Tasks 5/8); `AdConfig.nonPersonalizedRequest` used in Tasks 7/12 — consistent.

## Verification (end-to-end of this plan's scope)
- `git grep -n "under review" DECISIONS.md AGENTS.md` → no frontend-platform matches.
- `bash scripts/firewall-guard.sh` → exit 0; a Dart ad file referencing `event`/`child` → BLOCK (Task 2).
- `cd frontend && flutter test` → all unit + widget tests pass (Tasks 5–9).
- Phase 2 verified on device/emulator once accounts + backend endpoints exist.
