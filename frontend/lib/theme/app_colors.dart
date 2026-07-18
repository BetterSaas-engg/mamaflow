import 'package:flutter/material.dart';

/// The warm & friendly palette (spec 2026-07-17). Built from one seed —
/// "Mama Coral" — then warmed so surfaces read as soft cream rather than
/// Material 3's cool near-white.
abstract final class AppColors {
  /// Brand accent — soft terracotta-coral. Warm and caring, not alarm-red.
  static const Color seed = Color(0xFFF27E63);

  // Warm surface ramp (peach-tinted).
  static const Color _surface = Color(0xFFFFFBF7);
  static const Color _surfaceLowest = Color(0xFFFFFFFF);
  static const Color _surfaceLow = Color(0xFFFFF6F0);
  static const Color _surfaceContainer = Color(0xFFFDEFE8);
  static const Color _surfaceHigh = Color(0xFFFAE7DD);

  /// Light color scheme: coral-seeded, with warm surface overrides.
  static ColorScheme lightScheme() {
    final base = ColorScheme.fromSeed(
      seedColor: seed,
      brightness: Brightness.light,
    );
    return base.copyWith(
      surface: _surface,
      surfaceContainerLowest: _surfaceLowest,
      surfaceContainerLow: _surfaceLow,
      surfaceContainer: _surfaceContainer,
      surfaceContainerHigh: _surfaceHigh,
    );
  }
}
