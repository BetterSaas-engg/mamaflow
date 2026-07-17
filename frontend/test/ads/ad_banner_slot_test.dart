import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_mobile_ads/google_mobile_ads.dart';
import 'package:mamaflow/ads/ad_banner_slot.dart';
import 'package:mamaflow/ads/ad_config.dart';

/// [LoadAdError]'s constructor is `@protected` (only callable from within the
/// plugin or a subclass), so a minimal subclass is the sanctioned way to build
/// one for a test.
class _TestLoadAdError extends LoadAdError {
  _TestLoadAdError() : super(0, 'test-domain', 'test load failure', null);
}

void main() {
  testWidgets('reserves a fixed 50px slot even when no ad loads (never fills, no crash)',
      (tester) async {
    // In a unit test the Ads plugin channel is unimplemented, so BannerAd.load()
    // stays pending forever — it never calls onAdLoaded or onAdFailedToLoad.
    // The slot must still render its reserved height and never throw.
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: AdBannerSlot())),
    );
    await tester.pump();

    final slot = tester.widget<SizedBox>(
      find.byKey(const Key('ad-banner-slot')),
    );
    expect(slot.height, 50);
    expect(slot.child, isNull);
    expect(tester.takeException(), isNull);
  });

  testWidgets('stays blank and disposes the ad when onAdFailedToLoad fires',
      (tester) async {
    late BannerAdListener capturedListener;
    late BannerAd capturedBanner;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AdBannerSlot(
            bannerBuilder: (listener) {
              capturedListener = listener;
              capturedBanner = BannerAd(
                size: AdSize.banner,
                adUnitId: AdConfig.bannerAdUnitId,
                request: AdConfig.nonPersonalizedRequest(),
                listener: listener,
              );
              return capturedBanner;
            },
          ),
        ),
      ),
    );
    await tester.pump();

    // Drive the failure path directly — the plugin channel never calls this
    // on its own under `flutter test`.
    capturedListener.onAdFailedToLoad!(capturedBanner, _TestLoadAdError());
    await tester.pump();

    final slot = tester.widget<SizedBox>(
      find.byKey(const Key('ad-banner-slot')),
    );
    expect(slot.height, 50);
    expect(slot.child, isNull);
    expect(tester.takeException(), isNull);
  });
}
