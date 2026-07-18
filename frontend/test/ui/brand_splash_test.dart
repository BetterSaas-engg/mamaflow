import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/theme/app_logo.dart';
import 'package:mamaflow/ui/widgets/brand_splash.dart';

void main() {
  testWidgets('BrandSplash shows the logo and settles', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: BrandSplash()));
    await tester.pumpAndSettle(); // must settle: animation is one-shot
    expect(find.byType(AppLogo), findsOneWidget);
  });
}
