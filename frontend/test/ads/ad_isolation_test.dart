import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/ads/ad_config.dart';

/// THE FIREWALL (D19), enforced in BOTH directions:
///  - nothing outside lib/ads/ may touch the ad SDK, and
///  - nothing inside lib/ads/ may touch app code or content-shaped words.
/// The deterministic guard script only inspects ad-named paths, so this test
/// is the reverse-direction tripwire.
void main() {
  Iterable<File> dartFiles(String dir) => Directory(dir)
      .listSync(recursive: true)
      .whereType<File>()
      .where((f) => f.path.endsWith('.dart'));

  bool underAds(File f) => f.path.replaceAll('\\', '/').contains('lib/ads/');

  test('ad requests are non-personalized (npa=1, D21)', () {
    final req = AdConfig.nonPersonalizedRequest();
    expect(req.nonPersonalizedAds, true);
  });

  test('the ad SDK is imported ONLY under lib/ads/ (firewall D19)', () {
    final offenders = dartFiles('lib')
        .where((f) => !underAds(f))
        .where((f) => f.readAsStringSync().contains('google_mobile_ads'))
        .map((f) => f.path)
        .toList();
    expect(offenders, isEmpty,
        reason: 'ad SDK referenced outside lib/ads/: $offenders');
  });

  test('every file under lib/ads/ stays app- and content-free (firewall D19)',
      () {
    final adsFiles = dartFiles('lib/ads').toList();
    expect(adsFiles, isNotEmpty); // the scan must actually cover something

    for (final f in adsFiles) {
      final src = f.readAsStringSync();
      expect(src.contains('package:mamaflow/'), false,
          reason: '${f.path} imports app code');
      expect(src.contains("import '../"), false,
          reason: '${f.path} imports app code via a relative path');
      expect(RegExp(r'\b(event|child|extraction|email|item)\b').hasMatch(src),
          false,
          reason: '${f.path} references content-shaped identifiers');
    }
  });
}
