import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../items/item.dart';
import '../../items/items_controller.dart';
import '../../theme/category_colors.dart';
import '../../theme/tokens.dart';
import '../item_detail_screen.dart';

/// The warm rounded item card — the redesign's centerpiece, shared by the
/// Agenda and the Calendar's selected-day list. A leading category badge, the
/// title, small meta pills, and a status action. Swipe right = done, left =
/// dismiss (with haptics); the same actions live in the trailing menu.
///
/// FIREWALL note: this is presentation only. Category color/icon come from the
/// type label; nothing here reaches the ad layer.
class ItemCard extends ConsumerWidget {
  const ItemCard({
    super.key,
    required this.item,
    this.dense = false,
    this.showDate = true,
    this.interactive = true,
  });

  final Item item;
  final bool dense;
  final bool showDate;

  /// When false, drop the swipe/menu status affordances (tap-through only).
  /// The Calendar uses this: its day list watches `calendarItemsProvider`,
  /// which a status change on `itemsProvider` wouldn't refresh — so the swipe
  /// would look like a no-op. The Agenda keeps it true.
  final bool interactive;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    final closed = item.status == 'done' || item.status == 'dismissed';
    final accent = categoryColor(item.eventType);

    final card = Container(
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(AppRadii.lg),
        boxShadow: AppShadows.card,
      ),
      child: Material(
        type: MaterialType.transparency,
        child: InkWell(
          borderRadius: BorderRadius.circular(AppRadii.lg),
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => ItemDetailScreen(item: item)),
          ),
          child: Padding(
            padding: EdgeInsets.all(dense ? AppSpacing.md : AppSpacing.lg),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _Badge(accent: accent, icon: categoryIcon(item.eventType), closed: closed),
                const SizedBox(width: AppSpacing.md),
                Expanded(child: _content(context, scheme, closed, accent)),
                _trailing(context, ref, scheme, closed),
              ],
            ),
          ),
        ),
      ),
    );

    // No swipe on already-closed items or in non-interactive (calendar) mode.
    if (closed || !interactive) return card;
    return Dismissible(
      key: ValueKey('dismiss-${item.id}'),
      background: _swipeBg(scheme, Alignment.centerLeft, Icons.check_circle, scheme.primary),
      secondaryBackground:
          _swipeBg(scheme, Alignment.centerRight, Icons.inbox_rounded, scheme.tertiary),
      // Return false so the row snaps back; the provider refresh (inside
      // _setStatus) removes it cleanly — avoids the "dismissed widget still in
      // tree" crash that a true dismiss would hit with an async-backed list.
      confirmDismiss: (dir) async {
        HapticFeedback.mediumImpact();
        await _setStatus(context, ref,
            dir == DismissDirection.startToEnd ? 'done' : 'dismissed');
        return false;
      },
      child: card,
    );
  }

  Widget _content(BuildContext context, ColorScheme scheme, bool closed, Color accent) {
    final text = Theme.of(context).textTheme;
    final metaParts = <String>[
      if (showDate && item.date != null)
        [item.date, item.time].whereType<String>().join(' '),
      if (!showDate && item.time != null) item.time!,
      if (item.eventType != null) item.eventType!,
      if (item.childName != null) item.childName!,
    ].where((s) => s.isNotEmpty).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          item.title,
          style: text.titleMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: closed ? scheme.onSurfaceVariant : scheme.onSurface,
            decoration: closed ? TextDecoration.lineThrough : null,
          ),
        ),
        if (metaParts.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.sm),
          Wrap(
            spacing: AppSpacing.xs,
            runSpacing: AppSpacing.xs,
            children: [for (final m in metaParts) _MetaChip(label: m, accent: accent)],
          ),
        ],
      ],
    );
  }

  Widget _trailing(BuildContext context, WidgetRef ref, ColorScheme scheme, bool closed) {
    if (closed) {
      return Padding(
        padding: const EdgeInsets.only(left: AppSpacing.sm),
        child: Chip(
          label: Text(item.status),
          visualDensity: VisualDensity.compact,
          backgroundColor: scheme.surfaceContainerHigh,
        ),
      );
    }
    if (!interactive) return const SizedBox.shrink();
    return PopupMenuButton<String>(
      icon: Icon(Icons.more_vert, color: scheme.onSurfaceVariant),
      onSelected: (status) => _setStatus(context, ref, status),
      itemBuilder: (context) => const [
        PopupMenuItem(value: 'done', child: Text('Mark done')),
        PopupMenuItem(value: 'dismissed', child: Text('Dismiss')),
      ],
    );
  }

  Widget _swipeBg(ColorScheme scheme, Alignment align, IconData icon, Color color) => Container(
        decoration: BoxDecoration(
          color: color.withValues(alpha: .18),
          borderRadius: BorderRadius.circular(AppRadii.lg),
        ),
        alignment: align,
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl),
        child: Icon(icon, color: color),
      );

  Future<void> _setStatus(BuildContext context, WidgetRef ref, String status) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      HapticFeedback.selectionClick();
      await ref.read(itemsProvider.notifier).setStatus(item.id, status);
    } catch (_) {
      messenger.showSnackBar(
          const SnackBar(content: Text('Could not update the item.')));
    }
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.accent, required this.icon, required this.closed});
  final Color accent;
  final IconData icon;
  final bool closed;

  @override
  Widget build(BuildContext context) {
    final c = closed ? Theme.of(context).colorScheme.onSurfaceVariant : accent;
    return Container(
      width: 40,
      height: 40,
      decoration: BoxDecoration(color: c.withValues(alpha: .16), shape: BoxShape.circle),
      child: Icon(icon, color: c, size: 22),
    );
  }
}

class _MetaChip extends StatelessWidget {
  const _MetaChip({required this.label, required this.accent});
  final String label;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: AppSpacing.hair),
      decoration: BoxDecoration(
        color: accent.withValues(alpha: .10),
        borderRadius: BorderRadius.circular(AppRadii.pill),
      ),
      child: Text(
        label,
        style: text.labelSmall?.copyWith(
          color: Color.alphaBlend(accent.withValues(alpha: .9),
              Theme.of(context).colorScheme.onSurface),
        ),
      ),
    );
  }
}
