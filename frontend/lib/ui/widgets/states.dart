import 'package:flutter/material.dart';

import '../../theme/tokens.dart';

/// Friendly full-screen placeholders — a soft coral disc behind a glyph, a
/// warm title, a supporting line, and an optional action. Shared by the Agenda
/// and the Calendar so empty/error states feel cared-for, not broken.

class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    required this.message,
    this.actionLabel,
    this.onAction,
    this.compact = false,
  });

  final IconData icon;
  final String title;
  final String message;
  final String? actionLabel;
  final VoidCallback? onAction;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    // A min-height Column (no Center) so it's safe both inside a bounded box
    // (wrap in Center to place it) and inside a scroll view (tight day lists),
    // where a height-filling Center would overflow.
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: compact ? 64 : 96,
            height: compact ? 64 : 96,
            decoration: BoxDecoration(
              color: scheme.primaryContainer.withValues(alpha: .5),
              shape: BoxShape.circle,
            ),
            child: Icon(icon,
                size: compact ? 30 : 44, color: scheme.onPrimaryContainer),
          ),
          const SizedBox(height: AppSpacing.lg),
          Text(title, style: text.titleMedium, textAlign: TextAlign.center),
          const SizedBox(height: AppSpacing.sm),
          Text(
            message,
            style: text.bodyMedium?.copyWith(color: scheme.onSurfaceVariant),
            textAlign: TextAlign.center,
          ),
          if (actionLabel != null && onAction != null) ...[
            const SizedBox(height: AppSpacing.lg),
            FilledButton(onPressed: onAction, child: Text(actionLabel!)),
          ],
        ],
      ),
    );
  }
}

/// An error placeholder with a retry affordance. Message + action strings are
/// passed in so call sites keep their exact copy (tests assert on them).
class ErrorState extends StatelessWidget {
  const ErrorState({
    super.key,
    required this.message,
    required this.actionLabel,
    required this.onAction,
  });

  final String message;
  final String actionLabel;
  final VoidCallback onAction;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off_rounded, size: 44, color: scheme.onSurfaceVariant),
            const SizedBox(height: AppSpacing.md),
            Text(message,
                style: text.bodyLarge, textAlign: TextAlign.center),
            const SizedBox(height: AppSpacing.lg),
            FilledButton(onPressed: onAction, child: Text(actionLabel)),
          ],
        ),
      ),
    );
  }
}

/// A skeleton of pulsing card placeholders shown while items load. The pulse
/// repeats, but — like the [CircularProgressIndicator] it replaces — it only
/// lives during the transient loading state, so `pumpAndSettle` still settles
/// once real data arrives and this is torn down.
class LoadingState extends StatefulWidget {
  const LoadingState({super.key, this.count = 5});
  final int count;

  @override
  State<LoadingState> createState() => _LoadingStateState();
}

class _LoadingStateState extends State<LoadingState>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ListView.separated(
      padding: const EdgeInsets.all(AppSpacing.lg),
      itemCount: widget.count,
      separatorBuilder: (_, _) => const SizedBox(height: AppSpacing.sm),
      itemBuilder: (context, _) => FadeTransition(
        opacity: Tween(begin: 0.4, end: 0.9).animate(_c),
        child: Container(
          height: 76,
          decoration: BoxDecoration(
            color: scheme.surfaceContainerLow,
            borderRadius: BorderRadius.circular(AppRadii.lg),
          ),
        ),
      ),
    );
  }
}
