import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/core/providers.dart';

void main() {
  test('adsEnabled defaults to false when SHOW_ADS is unset', () {
    final c = ProviderContainer();
    addTearDown(c.dispose);
    expect(c.read(adsEnabledProvider), false);
  });

  test('adsEnabledProvider is overridable (the test/build seam)', () {
    final c = ProviderContainer(
      overrides: [adsEnabledProvider.overrideWithValue(true)],
    );
    addTearDown(c.dispose);
    expect(c.read(adsEnabledProvider), true);
  });
}
