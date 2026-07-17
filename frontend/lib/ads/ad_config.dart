import 'dart:io' show Platform;

import 'package:google_mobile_ads/google_mobile_ads.dart';

/// Ad layer. FIREWALL (D19): this file must never import app/feature models
/// or reference any user-derived data. Launch ads are non-personalized
/// (npa=1, D21). The prototype serves Google TEST ad units only — no real
/// serving, no revenue, no account.
class AdConfig {
  static AdRequest nonPersonalizedRequest() =>
      const AdRequest(nonPersonalizedAds: true);

  /// Google's public TEST banner unit (per platform). Real ad-unit ids are a
  /// launch-time swap; until then these guarantee test-only serving.
  static String get bannerAdUnitId => Platform.isIOS
      ? 'ca-app-pub-3940256099942544/2934735716'
      : 'ca-app-pub-3940256099942544/6300978111';

  /// Initialize the Mobile Ads SDK. Called only when ads are enabled.
  static Future<void> initialize() => MobileAds.instance.initialize();
}
