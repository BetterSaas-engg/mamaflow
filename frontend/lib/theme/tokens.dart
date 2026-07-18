import 'package:flutter/material.dart';

/// Design tokens for the warm & friendly redesign (spec 2026-07-17).
/// Every screen pulls spacing/radii/shadow/motion from here instead of inline
/// magic numbers, so the whole app stays visually consistent.

/// Spacing scale (logical px).
abstract final class AppSpacing {
  static const double hair = 2;
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double xxl = 32;
}

/// Corner radii. Cards use [lg]; chips/pills use [pill].
abstract final class AppRadii {
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double pill = 999;
}

/// Soft warm depth — used on cards (paired with elevation 0 so there's no
/// grey M3 elevation overlay, just a gentle shadow).
abstract final class AppShadows {
  static const List<BoxShadow> card = [
    BoxShadow(color: Color(0x14000000), blurRadius: 16, offset: Offset(0, 4)),
  ];
}

/// Motion durations. Kept short so the UI feels alive, never sluggish.
abstract final class AppDurations {
  static const Duration fast = Duration(milliseconds: 150);
  static const Duration medium = Duration(milliseconds: 250);
  static const Duration slow = Duration(milliseconds: 400);
}

/// Motion curves.
abstract final class AppCurves {
  static const Curve standard = Curves.easeOutCubic;
  static const Curve entrance = Curves.easeOut;
}
