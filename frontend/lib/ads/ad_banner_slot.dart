import 'dart:async';

import 'package:flutter/material.dart';
import 'package:google_mobile_ads/google_mobile_ads.dart';

import 'ad_config.dart';

/// A firewalled test-ad banner (D19: takes no app/user data). Always reserves a
/// fixed height so surrounding content never reflows when the ad fills; if the
/// ad fails or never loads, the reserved area simply stays blank.
class AdBannerSlot extends StatefulWidget {
  const AdBannerSlot({super.key, @visibleForTesting this.bannerBuilder});

  /// Test-only seam: overrides how the underlying [BannerAd] is constructed
  /// so a test can capture the [BannerAdListener] and invoke its callbacks
  /// directly. The ad plugin channel is unregistered under `flutter test`, so
  /// a real [BannerAd] never loads or fails on its own. Production code
  /// always uses the default builder, so behavior there is unchanged.
  @visibleForTesting
  final BannerAd Function(BannerAdListener listener)? bannerBuilder;

  @override
  State<AdBannerSlot> createState() => _AdBannerSlotState();
}

class _AdBannerSlotState extends State<AdBannerSlot> {
  static const double _height = 50;
  BannerAd? _banner;
  bool _loaded = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  static BannerAd _defaultBuilder(BannerAdListener listener) => BannerAd(
        size: AdSize.banner,
        adUnitId: AdConfig.bannerAdUnitId,
        request: AdConfig.nonPersonalizedRequest(),
        listener: listener,
      );

  void _load() {
    final listener = BannerAdListener(
      onAdLoaded: (_) {
        if (mounted) setState(() => _loaded = true);
      },
      // Load failure is non-fatal: dispose and leave the reserved slot blank.
      // Null out `_banner` so `State.dispose()` doesn't dispose it again.
      onAdFailedToLoad: (ad, _) {
        ad.dispose();
        _banner = null;
      },
    );
    final banner = (widget.bannerBuilder ?? _defaultBuilder)(listener);
    _banner = banner;
    // BannerAd.load() is `Future<void> load() async` — it never throws
    // synchronously, so a try/catch around the call below is dead code; any
    // genuine async load error is swallowed here instead. The no-throw/
    // no-reflow guarantee for this widget is structural: build() always
    // returns the reserved SizedBox regardless of load outcome.
    unawaited(banner.load().catchError((Object _) {}));
  }

  @override
  void dispose() {
    _banner?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      key: const Key('ad-banner-slot'),
      height: _height,
      child: (_loaded && _banner != null) ? AdWidget(ad: _banner!) : null,
    );
  }
}
