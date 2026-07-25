# App distribution — testers (Android + iOS)

Tester distribution only: **Firebase App Distribution** (Android) + **TestFlight** (iOS).
Public store launch is a later phase — it is gated on Google's restricted-scope OAuth
verification (E0): until then the OAuth app is in Testing mode and every tester's Google
account must be on the console test-user list (max 100).

Applies-to state: bundle/application id `com.bettersaas.mamaflow.mamaflow`, version in
`frontend/pubspec.yaml` (`1.0.0+1` — bump `+N` for every new build you upload).

## Build-time defines (both platforms)

Every distributable build needs:

```bash
--dart-define=API_BASE_URL=https://mamaflow-production.up.railway.app \
--dart-define=GOOGLE_IOS_CLIENT_ID=<the iOS OAuth client id>
```

## Tester caveats (tell your testers)

- Google sign-in works only for accounts on the OAuth consent screen's test-user list.
- `TOKEN_STORE_BACKEND=memory` on Railway: after a backend restart/deploy, testers must
  sign in again for sync to resume. (Goes away with the A1 Secret Manager unblock.)
- Ads are Google TEST ad units (flag-off by default) — real ids are a launch-time swap.

---

## Phase A — Android via Firebase App Distribution

Release signing reads `frontend/android/key.properties` (gitignored). Without it, release
builds silently fall back to DEBUG signing — fine for `flutter run --release`, never
distribute those.

**A1. Generate the upload keystore (once, keep forever + back it up):**

```bash
keytool -genkey -v \
  -keystore ~/mamaflow-upload.jks \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -alias mamaflow
```

Pick a strong password; store it in a password manager. Losing this file+password means
losing update continuity for every installed copy.

**A2. Create `frontend/android/key.properties`** (gitignored — never commit):

```properties
storeFile=/Users/<you>/mamaflow-upload.jks
storePassword=<store password>
keyAlias=mamaflow
keyPassword=<key password>
```

**A3. Build the release APK:**

```bash
cd frontend
flutter build apk --release \
  --dart-define=API_BASE_URL=https://mamaflow-production.up.railway.app \
  --dart-define=GOOGLE_IOS_CLIENT_ID=<ios client id>
# → build/app/outputs/flutter-apk/app-release.apk
```

**A4. Upload to Firebase App Distribution:**
Firebase console → your project → **App Distribution** → select the Android app →
**Get started / Upload** → drop `app-release.apk` → add a tester group (emails) →
distribute. Testers get an email; first-time they install the App Tester app and must
allow install-unknown-apps.

**A5. (Recommended) register the release SHA-1 in Firebase:**
`keytool -list -v -keystore ~/mamaflow-upload.jks -alias mamaflow | grep SHA1` →
Firebase console → Project settings → the Android app → Add fingerprint → re-download
`google-services.json` into `frontend/android/app/`. (Auth doesn't need it — D30 — but
Firebase services are cleaner with it.)

## Phase B — iOS via TestFlight

**B1. App Store Connect one-time setup** (appstoreconnect.apple.com):
1. Accept the license agreements (Business → Agreements).
2. developer.apple.com/account → Identifiers → register `com.bettersaas.mamaflow.mamaflow`
   with the **Push Notifications** capability checked.
3. developer.apple.com/account → Keys → create an **APNs key** (.p8), download it once,
   store safely. Upload it in Firebase console → Project settings → Cloud Messaging →
   the iOS app (this also unlocks Track B push).

**B2. Xcode (once):** open `frontend/ios/Runner.xcworkspace` →
1. Signing & Capabilities: sign in with the Apple account, select the team,
   "Automatically manage signing".
2. Drag `ios/Runner/GoogleService-Info.plist` into the Runner target (file exists on
   disk but is NOT in the Xcode project — objectVersion 54 = no auto-include).

**B3. Create the app record:** App Store Connect → My Apps → “+” → New App → platform
iOS, name Mamaflow, bundle id from B1, any SKU.

**B4. Build + upload — VERIFIED FLOW (2026-07-25, first upload).**

Xcode-account signing was unusable (fresh team, zero registered devices → no dev
profiles; portal membership sync lag), so releases use **manual distribution
signing driven by the App Store Connect API key** — the CI pattern. Standing
assets on the build Mac (all created 2026-07-25):

- ASC API key `mamaflow-ci` — Key ID `A76YMZ8L97`, Issuer
  `48456377-ecc9-4227-a214-c178134c255d`, file at
  `~/.appstoreconnect/private_keys/AuthKey_A76YMZ8L97.p8`
- Apple Distribution cert (serial `4D2AEE71…`, made via `POST /v1/certificates`)
  + private key, in keychain `mamaflow-build.keychain`; keychain password at
  `~/.appstoreconnect/mamaflow-build-keychain.pass`, cert private key backup at
  `~/.appstoreconnect/mamaflow-dist-cert-private.key`
- Provisioning profile **"Mamaflow AppStore"** (`IOS_APP_STORE`, via
  `POST /v1/profiles`) installed under `~/Library/MobileDevice/Provisioning
  Profiles/` — expires ~1 year; re-mint via the same API when it does
- `Runner` target **Release** config: `CODE_SIGN_STYLE=Manual`,
  `CODE_SIGN_IDENTITY=Apple Distribution`,
  `PROVISIONING_PROFILE_SPECIFIER=Mamaflow AppStore` (Debug/Profile stay
  Automatic). Committed in the repo.

Per release (bump `pubspec.yaml` version first):

```bash
cd frontend
security unlock-keychain -p "$(cat ~/.appstoreconnect/mamaflow-build-keychain.pass)" mamaflow-build.keychain
flutter build ios --release --no-codesign \
  --dart-define=API_BASE_URL=https://mamaflow-production.up.railway.app \
  --dart-define=GOOGLE_IOS_CLIENT_ID=<ios client id>
cd ios
xcodebuild -workspace Runner.xcworkspace -scheme Runner -configuration Release \
  archive -archivePath ../build/ios/archive/Runner.xcarchive \
  -destination 'generic/platform=iOS'
xcodebuild -exportArchive -archivePath ../build/ios/archive/Runner.xcarchive \
  -exportPath ../build/ios/ipa -exportOptionsPlist ../build/ExportOptions.plist
xcrun altool --upload-app -f ../build/ios/ipa/mamaflow.ipa -t ios \
  --apiKey A76YMZ8L97 --apiIssuer 48456377-ecc9-4227-a214-c178134c255d
```

(`frontend/build/ExportOptions.plist`: method `app-store-connect`, manual
signing, profile mapping — regenerate from this doc if `build/` was cleaned:
signingStyle manual, signingCertificate "Apple Distribution",
provisioningProfiles {bundle id → "Mamaflow AppStore"}.)

**B5. TestFlight:** App Store Connect → the app → TestFlight → the build appears after
processing (~15 min) → answer the export-compliance question (uses standard HTTPS only →
"standard encryption") → add **Internal Testers** (instant, up to 100) by inviting their
Apple-ID emails. External tester groups need a one-time light Beta App Review.

## Every subsequent build

1. Bump `version:` in `frontend/pubspec.yaml` (e.g. `1.0.0+2` — the `+N` is the
   Android versionCode / iOS build number; stores reject re-used numbers).
2. Rebuild (A3 / B4) and re-upload (A4 / B5).

## Store launch (later — do not start yet)

Blocked on E0: Google restricted-scope verification (CASA security assessment; needs the
privacy policy + homepage on themamaflow.com — live), plus Play Console ($25 one-time,
requires a closed-testing period for new personal accounts) and App Store review. Also:
swap AdMob test ids, `app-ads.txt`, real ad units (D21/D32).
