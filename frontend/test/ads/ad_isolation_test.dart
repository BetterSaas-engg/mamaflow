import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/ads/ad_config.dart';

void main() {
  test('ad requests are non-personalized (npa=1, D21)', () {
    final req = AdConfig.nonPersonalizedRequest();
    expect(req.nonPersonalizedAds, true);
  });

  test('ads source imports nothing from features / item models (firewall D19)', () {
    final src = File('lib/ads/ad_config.dart').readAsStringSync();
    expect(src.contains('package:mamaflow/features'), false);
    expect(src.contains('family_event'), false);
    expect(RegExp(r'\b(event|child|extraction|email)\b').hasMatch(src), false);
  });
}
