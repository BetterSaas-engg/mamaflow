import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/theme/app_logo.dart';

void main() {
  testWidgets('AppLogo builds and paints at both styles without throwing',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              AppLogo(size: 96),
              AppLogo(size: 40, style: AppLogoStyle.whiteOnCoral),
            ],
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byType(AppLogo), findsNWidgets(2));
    expect(tester.takeException(), isNull);
  });
}
