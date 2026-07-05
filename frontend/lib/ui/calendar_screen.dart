import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../calendar/calendar_math.dart';
import '../items/item.dart';
import '../items/items_controller.dart';
import 'item_detail_screen.dart';

const _monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

String _iso(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

bool _sameDay(DateTime a, DateTime b) =>
    a.year == b.year && a.month == b.month && a.day == b.day;

/// Month calendar over the loaded items: dots on days with items, tap a day to
/// list its items. Dateless to-dos stay in the Agenda tab.
class CalendarScreen extends ConsumerStatefulWidget {
  const CalendarScreen({super.key});
  @override
  ConsumerState<CalendarScreen> createState() => _CalendarScreenState();
}

class _CalendarScreenState extends ConsumerState<CalendarScreen> {
  late DateTime _visible; // first of the visible month
  DateTime? _selected;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _visible = DateTime(now.year, now.month);
    _selected = DateTime(now.year, now.month, now.day);
  }

  void _shiftMonth(int delta) => setState(() {
        _visible = DateTime(_visible.year, _visible.month + delta);
      });

  void _today() => setState(() {
        final now = DateTime.now();
        _visible = DateTime(now.year, now.month);
        _selected = DateTime(now.year, now.month, now.day);
      });

  @override
  Widget build(BuildContext context) {
    final items = ref.watch(itemsProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text('${_monthNames[_visible.month - 1]} ${_visible.year}'),
        actions: [
          IconButton(
            tooltip: 'Previous month',
            icon: const Icon(Icons.chevron_left),
            onPressed: () => _shiftMonth(-1),
          ),
          IconButton(
            tooltip: 'Next month',
            icon: const Icon(Icons.chevron_right),
            onPressed: () => _shiftMonth(1),
          ),
          TextButton(onPressed: _today, child: const Text('Today')),
        ],
      ),
      body: items.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => const Center(child: Text('Could not load items.')),
        data: (list) => _calendar(context, list),
      ),
    );
  }

  Widget _calendar(BuildContext context, List<Item> list) {
    final byDate = itemsByDate(list);
    final cells = monthGrid(_visible.year, _visible.month);
    final today = DateTime.now();
    final selectedItems =
        _selected == null ? const <Item>[] : (byDate[_iso(_selected!)] ?? const <Item>[]);

    return Column(
      children: [
        const _WeekdayHeader(),
        GridView.count(
          crossAxisCount: 7,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          childAspectRatio: 2,
          children: [
            for (final cell in cells)
              if (cell == null)
                const SizedBox.shrink()
              else
                _DayCell(
                  day: cell.day,
                  isToday: _sameDay(cell, today),
                  isSelected: _selected != null && _sameDay(cell, _selected!),
                  hasItems: byDate.containsKey(_iso(cell)),
                  onTap: () => setState(() => _selected = cell),
                ),
          ],
        ),
        const Divider(height: 1),
        Expanded(
          child: selectedItems.isEmpty
              ? const Center(child: Text('No items on this day.'))
              : ListView.separated(
                  itemCount: selectedItems.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (context, i) => _DayItemTile(item: selectedItems[i]),
                ),
        ),
      ],
    );
  }
}

class _WeekdayHeader extends StatelessWidget {
  const _WeekdayHeader();
  @override
  Widget build(BuildContext context) => Row(
        children: [
          for (final d in const ['S', 'M', 'T', 'W', 'T', 'F', 'S'])
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Text(d,
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 11, color: Colors.grey)),
              ),
            ),
        ],
      );
}

class _DayCell extends StatelessWidget {
  const _DayCell({
    required this.day,
    required this.isToday,
    required this.isSelected,
    required this.hasItems,
    required this.onTap,
  });
  final int day;
  final bool isToday;
  final bool isSelected;
  final bool hasItems;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: isSelected ? scheme.primaryContainer : null,
          border: isToday ? Border.all(color: scheme.primary) : null,
          borderRadius: BorderRadius.circular(8),
        ),
        margin: const EdgeInsets.all(2),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text('$day'),
            const SizedBox(height: 2),
            Container(
              width: 6,
              height: 6,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: hasItems ? scheme.primary : Colors.transparent,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DayItemTile extends StatelessWidget {
  const _DayItemTile({required this.item});
  final Item item;

  @override
  Widget build(BuildContext context) {
    final subtitle = <String>[
      if (item.time != null) item.time!,
      if (item.eventType != null) item.eventType!,
      if (item.childName != null) item.childName!,
    ].join('  ·  ');
    return ListTile(
      leading: Icon(item.isEvent ? Icons.event : Icons.check_circle_outline),
      title: Text(item.title),
      subtitle: subtitle.isEmpty ? null : Text(subtitle),
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => ItemDetailScreen(item: item)),
      ),
    );
  }
}
