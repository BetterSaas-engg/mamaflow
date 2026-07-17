import 'package:flutter/material.dart';
import 'package:google_mobile_ads/google_mobile_ads.dart';

import 'ad_config.dart';

/// A firewalled test-ad banner (D19: takes no app/user data). Always reserves a
/// fixed height so surrounding content never reflows when the ad fills; if the
/// ad fails or never loads, the reserved area simply stays blank.
class AdBannerSlot extends StatefulWidget {
  const AdBannerSlot({super.key});

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

  void _load() {
    final banner = BannerAd(
      size: AdSize.banner,
      adUnitId: AdConfig.bannerAdUnitId,
      request: AdConfig.nonPersonalizedRequest(),
      listener: BannerAdListener(
        onAdLoaded: (_) {
          if (mounted) setState(() => _loaded = true);
        },
        // Load failure is non-fatal: dispose and leave the reserved slot blank.
        onAdFailedToLoad: (ad, _) => ad.dispose(),
      ),
    );
    _banner = banner;
    // Best-effort: a missing plugin/channel (e.g. tests) must never throw.
    try {
      banner.load();
    } catch (_) {}
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
