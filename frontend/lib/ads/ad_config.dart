import 'package:google_mobile_ads/google_mobile_ads.dart';

/// Ad layer. FIREWALL (D19): this file must never import app/feature models
/// or reference any user-derived data. Launch ads are non-personalized
/// (npa=1, D21).
class AdConfig {
  static AdRequest nonPersonalizedRequest() =>
      const AdRequest(nonPersonalizedAds: true);
}
