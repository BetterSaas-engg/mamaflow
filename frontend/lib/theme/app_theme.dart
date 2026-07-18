import 'package:flutter/material.dart';

import 'app_colors.dart';
import 'tokens.dart';

/// The Mamaflow app theme — warm & friendly (spec 2026-07-17). Building the
/// whole [ThemeData] here (colors + Nunito/Fredoka type + component themes +
/// page transitions) means every screen inherits the redesign with no
/// call-site changes. Ship light-only for now; [buildDarkTheme] is a stub for
/// the documented dark-mode fast-follow.

ThemeData buildLightTheme() => _buildTheme(AppColors.lightScheme());

/// Dark-theme stub (fast-follow). Same builder, dark scheme — not wired yet.
ThemeData buildDarkTheme() => _buildTheme(
      ColorScheme.fromSeed(seedColor: AppColors.seed, brightness: Brightness.dark),
    );

ThemeData _buildTheme(ColorScheme scheme) {
  final textTheme = _textTheme(scheme);
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: scheme.surface,
    textTheme: textTheme,
    // Body/UI font everywhere by default; headlines override to Fredoka below.
    fontFamily: 'Nunito',
    pageTransitionsTheme: const PageTransitionsTheme(
      builders: {
        TargetPlatform.android: _FadeSlideUp(),
        TargetPlatform.iOS: _FadeSlideUp(),
        TargetPlatform.macOS: _FadeSlideUp(),
      },
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      color: scheme.surfaceContainerLow,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadii.lg),
      ),
    ),
    chipTheme: ChipThemeData(
      shape: const StadiumBorder(),
      side: BorderSide.none,
      backgroundColor: scheme.surfaceContainerHigh,
      selectedColor: scheme.primaryContainer,
      labelStyle: textTheme.labelLarge,
      showCheckmark: false,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: scheme.surface,
      foregroundColor: scheme.onSurface,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: textTheme.titleLarge,
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: scheme.surfaceContainer,
      indicatorColor: scheme.primaryContainer,
      elevation: 0,
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      labelTextStyle: WidgetStatePropertyAll(textTheme.labelMedium),
    ),
    floatingActionButtonTheme: FloatingActionButtonThemeData(
      backgroundColor: scheme.primary,
      foregroundColor: scheme.onPrimary,
      elevation: 2,
      shape: const StadiumBorder(),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadii.pill),
        ),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.xl,
          vertical: AppSpacing.md,
        ),
      ),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: scheme.inverseSurface,
      contentTextStyle: textTheme.bodyMedium?.copyWith(color: scheme.onInverseSurface),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadii.md),
      ),
    ),
    dividerTheme: DividerThemeData(
      color: scheme.outlineVariant,
      thickness: 1,
      space: 1,
    ),
    listTileTheme: const ListTileThemeData(
      contentPadding: EdgeInsets.symmetric(horizontal: AppSpacing.lg),
    ),
  );
}

/// Body text in Nunito; display/headline/titleLarge in Fredoka (the friendly
/// rounded brand face). Variable fonts, so `fontWeight` drives the wght axis.
TextTheme _textTheme(ColorScheme scheme) {
  final base = ThemeData(brightness: scheme.brightness)
      .textTheme
      .apply(fontFamily: 'Nunito', bodyColor: scheme.onSurface, displayColor: scheme.onSurface);
  TextStyle? fredoka(TextStyle? s, {FontWeight weight = FontWeight.w600}) =>
      s?.copyWith(fontFamily: 'Fredoka', fontWeight: weight);
  return base.copyWith(
    displayLarge: fredoka(base.displayLarge),
    displayMedium: fredoka(base.displayMedium),
    displaySmall: fredoka(base.displaySmall),
    headlineLarge: fredoka(base.headlineLarge),
    headlineMedium: fredoka(base.headlineMedium),
    headlineSmall: fredoka(base.headlineSmall),
    titleLarge: fredoka(base.titleLarge),
  );
}

/// Page transition: a gentle fade + slide-up applied to every push app-wide.
class _FadeSlideUp extends PageTransitionsBuilder {
  const _FadeSlideUp();

  @override
  Widget buildTransitions<T>(
    PageRoute<T> route,
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) {
    final curved = CurvedAnimation(parent: animation, curve: AppCurves.standard);
    return FadeTransition(
      opacity: curved,
      child: SlideTransition(
        position: Tween<Offset>(
          begin: const Offset(0, 0.03),
          end: Offset.zero,
        ).animate(curved),
        child: child,
      ),
    );
  }
}
