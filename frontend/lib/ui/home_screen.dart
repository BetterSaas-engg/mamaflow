import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../items/filters.dart';
import '../items/grouping.dart';
import '../items/item.dart';
import '../items/items_controller.dart';
import '../items/sync_service.dart';
import '../theme/tokens.dart';
import 'settings_screen.dart';
import 'widgets/filter_chip_bar.dart';
import 'widgets/item_card.dart';
import 'widgets/section_header.dart';
import 'widgets/states.dart';
import 'widgets/sync_progress_card.dart';

/// The signed-in home: the user's items as a grouped agenda (Overdue / Today /
/// This week / Later / To-do), filterable by child/type, with a "Show
/// completed" toggle. Rows tap through to [ItemDetailScreen].
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});
  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  String? _child; // single-select chip: one of child/type is set at a time
  String? _type;
  bool _completed = false;
  SyncStatus? _syncStatus; // non-null while a sync is in flight

  // Stable first-seen rank per item id, so the staggered entrance delay (and
  // thus flutter_animate's total duration) never changes for an already-visible
  // card. Keying the stagger to the live list index instead made a filter tap
  // or "show completed" toggle restart every settled card's fade — a flicker.
  final Map<String, int> _entranceRank = {};
  int _rankFor(String id) => _entranceRank.putIfAbsent(id, () => _entranceRank.length);

  @override
  Widget build(BuildContext context) {
    final items = ref.watch(itemsProvider);
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        icon: const Icon(Icons.sync),
        label: const Text('Sync inbox'),
        onPressed: () => _sync(context),
      ),
      appBar: AppBar(
        title: const Text('Mamaflow'),
        actions: [
          IconButton(
            tooltip: _completed ? 'Show open' : 'Show completed',
            icon: Icon(_completed ? Icons.inbox : Icons.done_all),
            onPressed: () {
              setState(() => _completed = !_completed);
              ref.read(itemsProvider.notifier).showCompleted(_completed);
            },
          ),
          IconButton(
            tooltip: 'Settings',
            icon: const Icon(Icons.settings),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const SettingsScreen()),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          if (_syncStatus != null) SyncProgressCard(status: _syncStatus!),
          Expanded(
            child: items.when(
              loading: () => const LoadingState(),
              error: (e, _) => ErrorState(
                message: 'Could not load items.',
                actionLabel: 'Retry',
                onAction: () => ref.read(itemsProvider.notifier).refresh(),
              ),
              data: (list) => RefreshIndicator(
                onRefresh: () => ref.read(itemsProvider.notifier).refresh(),
                child: _body(list),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _body(List<Item> all) {
    final filtered = applyChipFilter(all, child: _child, type: _type);
    final sections = groupItems(filtered, DateTime.now());
    final children = childValues(all);
    final types = typeValues(all);

    return CustomScrollView(
      slivers: [
        if (children.isNotEmpty || types.isNotEmpty)
          SliverToBoxAdapter(
            child: FilterChipBar(
              children: children,
              types: types,
              selectedChild: _child,
              selectedType: _type,
              onSelectAll: () => setState(() { _child = null; _type = null; }),
              onSelectChild: (c) => setState(() { _child = c; _type = null; }),
              onSelectType: (t) => setState(() { _type = t; _child = null; }),
            ),
          ),
        if (sections.isEmpty)
          const SliverFillRemaining(
            hasScrollBody: false,
            child: Center(
              child: EmptyState(
                icon: Icons.check_circle_outline,
                title: 'No items yet',
                message: 'Pull down to refresh, or tap Sync inbox to scan your email.',
              ),
            ),
          ),
        for (final section in sections) ...[
          SliverToBoxAdapter(
            child: SectionHeader(title: section.title, count: section.items.length),
          ),
          SliverPadding(
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
            sliver: SliverList.builder(
              itemCount: section.items.length,
              itemBuilder: (context, i) {
                final item = section.items[i];
                return Padding(
                  key: ValueKey(item.id),
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: _entrance(_rankFor(item.id), ItemCard(item: item)),
                );
              },
            ),
          ),
        ],
        const SliverToBoxAdapter(child: SizedBox(height: AppSpacing.xxl)),
      ],
    );
  }

  /// One-shot fade + slide-up, staggered by position and capped so a long list
  /// (and `pumpAndSettle`) both stay bounded.
  Widget _entrance(int index, Widget child) => child
      .animate()
      .fadeIn(duration: AppDurations.medium, delay: (index.clamp(0, 10) * 40).ms)
      .slideY(
        begin: 0.08,
        end: 0,
        duration: AppDurations.medium,
        curve: AppCurves.entrance,
      );

  Future<void> _sync(BuildContext context) async {
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _syncStatus = const SyncStatus(status: 'running'));
    try {
      await for (final s in ref.read(syncServiceProvider).run()) {
        if (s.status == 'failed') {
          throw SyncFailedException(s.error ?? 'Sync failed. Try again.');
        }
        setState(() => _syncStatus = s);
      }
      final created = _syncStatus?.itemsCreated ?? 0;
      await ref.read(itemsProvider.notifier).refresh();
      ref.invalidate(calendarItemsProvider);
      setState(() => _syncStatus = null);
      messenger.showSnackBar(SnackBar(content: Text('Synced — $created new item(s)')));
    } on SyncFailedException catch (e) {
      setState(() => _syncStatus = null);
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    } catch (_) {
      setState(() => _syncStatus = null);
      messenger.showSnackBar(const SnackBar(content: Text('Sync failed. Try again.')));
    }
  }
}
