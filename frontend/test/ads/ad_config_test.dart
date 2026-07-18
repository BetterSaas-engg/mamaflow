import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/ads/ad_config.dart';

void main() {
  test('bannerAdUnitId is a Google test unit (never a real/monetizing id)', () {
    final id = AdConfig.bannerAdUnitId;
    expect(id, isNotEmpty);
    // Google's public test publisher id — guarantees no real serving/revenue.
    expect(id.startsWith('ca-app-pub-3940256099942544/'), true,
        reason: 'must be a Google TEST ad unit, got: $id');
  });

  test('ad requests stay non-personalized (npa=1, D21)', () {
    expect(AdConfig.nonPersonalizedRequest().nonPersonalizedAds, true);
  });
}
