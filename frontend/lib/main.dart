import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Reads the native FCM config (google-services.json / GoogleService-Info.plist).
  // Best-effort: a missing/misconfigured Firebase project must not block the app
  // (reminders are additive; the rest of the app works without them).
  try {
    await Firebase.initializeApp();
  } catch (_) {}
  runApp(const ProviderScope(child: MamaflowApp()));
}
