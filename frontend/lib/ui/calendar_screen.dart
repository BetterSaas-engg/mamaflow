import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../calendar/calendar_math.dart';
import '../items/item.dart';
import '../items/items_controller.dart';
import '../theme/category_colors.dart';
import '../theme/tokens.dart';
import 'widgets/item_card.dart';
import 'widgets/states.dart';

const _monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const _weekdayNames = [
  'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
];

String _iso(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

String _dayHeading(DateTime d) =>
    '${_weekdayNames[d.weekday - 1]}, ${_monthNames[d.month - 1]} ${d.day}';

bool _sameDay(DateTime a, DateTime b) =>
    a.year == b.year && a.month == b.month && a.day == b.day;

/// Month calendar over the loaded items: category-colored dots on days with
/// items, tap a day to list its items. Dateless to-dos stay in the Agenda tab.
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
    final items = ref.watch(calendarItemsProvider);
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
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
          child: GridView.count(
            crossAxisCount: 7,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            // Keep rows short enough that the month grid + day list fit the
            // Column without overflowing (cells hold a number + up to 3 dots).
            childAspectRatio: 1.8,
            children: [
              for (final cell in cells)
                if (cell == null)
                  const SizedBox.shrink()
                else
                  _DayCell(
                    day: cell.day,
                    isToday: _sameDay(cell, today),
                    isSelected: _selected != null && _sameDay(cell, _selected!),
                    items: byDate[_iso(cell)] ?? const <Item>[],
                    onTap: () => setState(() => _selected = cell),
                  ),
            ],
          ),
        ),
        const Divider(),
        Expanded(child: _dayList(selectedItems)),
      ],
    );
  }

  Widget _dayList(List<Item> selectedItems) {
    if (_selected == null) {
      return const SizedBox.shrink();
    }
    // One scroll view for the header + day items (or the empty state), so a
    // tight remaining height just scrolls instead of overflowing the Column.
    return ListView(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg, AppSpacing.md, AppSpacing.lg, AppSpacing.xxl),
      children: [
        Text(
          _dayHeading(_selected!),
          style: Theme.of(context).textTheme.titleSmall,
        ),
        const SizedBox(height: AppSpacing.sm),
        if (selectedItems.isEmpty)
          const EmptyState(
            icon: Icons.event_available_outlined,
            title: 'Nothing planned',
            message: 'No items on this day.',
            compact: true,
          )
        else
          for (final item in selectedItems)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
              child: ItemCard(
                item: item,
                dense: true,
                showDate: false,
                interactive: false,
              ),
            ),
      ],
    );
  }
}

class _WeekdayHeader extends StatelessWidget {
  const _WeekdayHeader();
  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    return Row(
      children: [
        for (final d in const ['S', 'M', 'T', 'W', 'T', 'F', 'S'])
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
              child: Text(d,
                  textAlign: TextAlign.center,
                  style: text.labelMedium?.copyWith(color: scheme.onSurfaceVariant)),
            ),
          ),
      ],
    );
  }
}

class _DayCell extends StatelessWidget {
  const _DayCell({
    required this.day,
    required this.isToday,
    required this.isSelected,
    required this.items,
    required this.onTap,
  });
  final int day;
  final bool isToday;
  final bool isSelected;
  final List<Item> items;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    // Up to three category-colored dots for the day's items.
    final dots = [
      for (final item in items.take(3)) categoryColor(item.eventType),
    ];
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: AppDurations.fast,
        curve: AppCurves.standard,
        margin: const EdgeInsets.all(AppSpacing.xs),
        decoration: BoxDecoration(
          color: isSelected ? scheme.primaryContainer : Colors.transparent,
          borderRadius: BorderRadius.circular(AppRadii.md),
        ),
        child: FittedBox(
          fit: BoxFit.scaleDown,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 30,
                height: 30,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: isToday
                      ? Border.all(color: scheme.primary, width: 2)
                      : null,
                ),
                child: Text('$day',
                    style: TextStyle(
                      fontWeight:
                          isToday || isSelected ? FontWeight.w700 : FontWeight.w500,
                      color: isSelected
                          ? scheme.onPrimaryContainer
                          : scheme.onSurface,
                    )),
              ),
              const SizedBox(height: AppSpacing.xs),
              SizedBox(
                height: 6,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    for (final c in dots)
                      Container(
                        width: 5,
                        height: 5,
                        margin: const EdgeInsets.symmetric(horizontal: 1),
                        decoration: BoxDecoration(shape: BoxShape.circle, color: c),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
