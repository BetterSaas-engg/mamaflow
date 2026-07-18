import 'package:flutter/material.dart';

import '../../items/sync_service.dart';
import '../../theme/tokens.dart';

/// The in-flight sync banner: a warm card with a rounded progress bar. Same
/// [SyncStatus] data as before, restyled to the design system.
class SyncProgressCard extends StatelessWidget {
  const SyncProgressCard({super.key, required this.status});
  final SyncStatus status;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    final total = status.toProcess;
    final done = status.processed;
    final value = (total != null && total > 0 && done != null) ? done / total : null;
    final line = total == null
        ? 'Syncing your inbox…'
        : 'Scanned ${status.messagesScanned ?? 0} · processed ${done ?? 0} / $total · ${status.itemsCreated ?? 0} items';

    return Container(
      margin: const EdgeInsets.fromLTRB(
          AppSpacing.lg, AppSpacing.md, AppSpacing.lg, 0),
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(AppRadii.lg),
        boxShadow: AppShadows.card,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(
                    strokeWidth: 2, color: scheme.primary),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(child: Text(line, style: text.bodySmall)),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          ClipRRect(
            borderRadius: BorderRadius.circular(AppRadii.pill),
            child: LinearProgressIndicator(
              value: value,
              minHeight: 6,
              backgroundColor: scheme.surfaceContainerHigh,
            ),
          ),
        ],
      ),
    );
  }
}
