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
