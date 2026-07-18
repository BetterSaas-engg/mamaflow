import 'package:flutter/material.dart';

import '../../theme/tokens.dart';

/// The horizontal child/type filter row. Single-select: choosing a child
/// clears any type and vice-versa; "All" clears both. Still built from real
/// [FilterChip] widgets (a test looks them up by label) — this only restyles
/// and lays them out, animating the selected pop.
class FilterChipBar extends StatelessWidget {
  const FilterChipBar({
    super.key,
    required this.children,
    required this.types,
    required this.selectedChild,
    required this.selectedType,
    required this.onSelectAll,
    required this.onSelectChild,
    required this.onSelectType,
  });

  final List<String> children;
  final List<String> types;
  final String? selectedChild;
  final String? selectedType;
  final VoidCallback onSelectAll;
  final ValueChanged<String> onSelectChild;
  final ValueChanged<String> onSelectType;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.sm),
      child: Row(
        children: [
          _Chip(
            label: 'All',
            selected: selectedChild == null && selectedType == null,
            onSelected: (_) => onSelectAll(),
          ),
          for (final c in children) ...[
            const SizedBox(width: AppSpacing.sm),
            _Chip(
              label: c,
              selected: selectedChild == c,
              onSelected: (_) => onSelectChild(c),
            ),
          ],
          for (final t in types) ...[
            const SizedBox(width: AppSpacing.sm),
            _Chip(
              label: t,
              selected: selectedType == t,
              onSelected: (_) => onSelectType(t),
            ),
          ],
        ],
      ),
    );
  }
}

/// A single selectable chip with a subtle scale pop when selected. Kept a real
/// [FilterChip] so widget lookups by (FilterChip, label) still resolve.
class _Chip extends StatelessWidget {
  const _Chip({required this.label, required this.selected, required this.onSelected});
  final String label;
  final bool selected;
  final ValueChanged<bool> onSelected;

  @override
  Widget build(BuildContext context) {
    return AnimatedScale(
      scale: selected ? 1.05 : 1.0,
      duration: AppDurations.fast,
      curve: AppCurves.standard,
      child: FilterChip(
        label: Text(label),
        selected: selected,
        onSelected: onSelected,
      ),
    );
  }
}
