import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/ads/ad_banner_slot.dart';

void main() {
  testWidgets('reserves a fixed 50px slot even when no ad loads (no reflow, no crash)',
      (tester) async {
    // In a unit test the Ads plugin channel is unimplemented, so the banner
    // never fills — the slot must still render its reserved height and never throw.
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: AdBannerSlot())),
    );
    await tester.pump();

    final slot = tester.widget<SizedBox>(
      find.byKey(const Key('ad-banner-slot')),
    );
    expect(slot.height, 50);
    expect(tester.takeException(), isNull);
  });
}
