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
