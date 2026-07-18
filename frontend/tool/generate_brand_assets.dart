// frontend/tool/generate_brand_assets.dart
//
// Dev tool (NOT part of the CI test run — lives in tool/, not test/).
// Regenerate the brand PNGs from the AppLogo vector:
//   cd frontend && flutter test tool/generate_brand_assets.dart
//
import 'dart:io';
import 'dart:typed_data';
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
      (await tester.runAsync<ByteData?>(() => image.toByteData(format: ui.ImageByteFormat.png)))!;
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
