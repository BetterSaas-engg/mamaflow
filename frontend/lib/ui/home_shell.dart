import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../ads/ad_banner_slot.dart';
import '../core/providers.dart';
import 'calendar_screen.dart';
import 'home_screen.dart';

/// The signed-in shell body with an optional anchored ad slot below the
/// content. Extracted so the flag-conditional is unit-testable without pumping
/// the full screen stack. FIREWALL: passes the slot no content data.
Widget adAnchoredBody({required bool showAds, required Widget content}) {
  return Column(
    children: [
      Expanded(child: content),
      if (showAds) const AdBannerSlot(),
    ],
  );
}

/// Signed-in shell: a bottom nav switching between the Agenda (grouped list)
/// and the month Calendar. IndexedStack keeps each tab's state.
class HomeShell extends ConsumerStatefulWidget {
  const HomeShell({super.key});
  @override
  ConsumerState<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends ConsumerState<HomeShell> {
  int _index = 0;

  @override
  void initState() {
    super.initState();
    // Register this device for reminder push once we're in the signed-in shell.
    // Idempotent and best-effort; failures never surface to the UI.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(pushServiceProvider).start();
    });
  }

  @override
  Widget build(BuildContext context) {
    final showAds = ref.watch(adsEnabledProvider);
    return Scaffold(
      body: adAnchoredBody(
        showAds: showAds,
        content: IndexedStack(
          index: _index,
          children: const [HomeScreen(), CalendarScreen()],
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.list_alt), label: 'Agenda'),
          NavigationDestination(icon: Icon(Icons.calendar_month), label: 'Calendar'),
        ],
      ),
    );
  }
}
