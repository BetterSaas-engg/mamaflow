import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import 'item.dart';
import 'items_service.dart';
import 'sync_service.dart';

final itemsServiceProvider =
    Provider<ItemsService>((ref) => ItemsService(ref.watch(apiClientProvider)));

final syncServiceProvider =
    Provider<SyncService>((ref) => SyncService(ref.watch(apiClientProvider)));

/// Loads the user's items and exposes mutations (mark done/dismiss) that
/// refresh the list. Backed by GET/PATCH /api/v1/items.
class ItemsController extends AsyncNotifier<List<Item>> {
  @override
  Future<List<Item>> build() => ref.read(itemsServiceProvider).list();

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() => ref.read(itemsServiceProvider).list());
  }

  Future<void> setStatus(String id, String status) async {
    await ref.read(itemsServiceProvider).updateStatus(id, status);
    await refresh();
  }
}

final itemsProvider =
    AsyncNotifierProvider<ItemsController, List<Item>>(ItemsController.new);
