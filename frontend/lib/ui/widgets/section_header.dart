import 'package:flutter/material.dart';

import '../../theme/tokens.dart';

/// A grouped-agenda section label (e.g. "Overdue", "Today"). The title string
/// still comes from the grouping logic unchanged; this only styles it.
class SectionHeader extends StatelessWidget {
  const SectionHeader({super.key, required this.title, this.count});

  final String title;
  final int? count;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg, AppSpacing.xl, AppSpacing.lg, AppSpacing.sm),
      child: Row(
        children: [
          // Render the title verbatim (no .toUpperCase()) — the grouping
          // titles ('Later', 'To-do — no date') are asserted exactly by tests.
          Text(
            title,
            style: text.labelMedium?.copyWith(
              color: scheme.onSurfaceVariant,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.4,
            ),
          ),
          if (count != null) ...[
            const SizedBox(width: AppSpacing.sm),
            Container(
              padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.sm, vertical: 1),
              decoration: BoxDecoration(
                color: scheme.surfaceContainerHigh,
                borderRadius: BorderRadius.circular(AppRadii.pill),
              ),
              child: Text('$count',
                  style: text.labelSmall?.copyWith(color: scheme.onSurfaceVariant)),
            ),
          ],
        ],
      ),
    );
  }
}
