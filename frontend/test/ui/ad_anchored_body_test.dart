import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/ads/ad_banner_slot.dart';
import 'package:mamaflow/ui/home_shell.dart';

void main() {
  testWidgets('adAnchoredBody omits the ad slot when showAds is false',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: adAnchoredBody(showAds: false, content: const Placeholder()),
      ),
    ));
    expect(find.byType(AdBannerSlot), findsNothing);
    expect(find.byType(Placeholder), findsOneWidget);
  });

  testWidgets('adAnchoredBody includes the ad slot when showAds is true',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: adAnchoredBody(showAds: true, content: const Placeholder()),
      ),
    ));
    await tester.pump();
    expect(find.byType(AdBannerSlot), findsOneWidget);
    expect(find.byType(Placeholder), findsOneWidget);
  });
}
