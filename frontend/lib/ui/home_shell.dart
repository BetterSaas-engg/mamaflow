import 'package:flutter/material.dart';

import 'calendar_screen.dart';
import 'home_screen.dart';

/// Signed-in shell: a bottom nav switching between the Agenda (grouped list)
/// and the month Calendar. IndexedStack keeps each tab's state.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});
  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _index,
        children: const [HomeScreen(), CalendarScreen()],
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
