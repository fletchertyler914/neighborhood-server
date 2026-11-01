package com.neighborhood.agent;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Material;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.block.Action;
import org.bukkit.event.block.BlockBreakEvent;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.inventory.EquipmentSlot;
import org.bukkit.inventory.ItemStack;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * QA campus demote / re-promote via dedicated items.
 * Left-click (or creative break) with demote item → demote.
 * Right-click with promote item (default: same hoe) → undo demote.
 */
final class QaDemoteListener implements Listener {
    private static final String PERMISSION = "neighborhood.agent.qa";
    private static final long DEBOUNCE_MS = 400L;

    private final NeighborhoodAgentPlugin plugin;
    private final QaGridIndex grid;
    private final QaDemotionStore store;
    private final Material demoteItem;
    private final Material promoteItem;
    private final Map<UUID, Long> debounce = new ConcurrentHashMap<>();

    QaDemoteListener(
            NeighborhoodAgentPlugin plugin,
            QaGridIndex grid,
            QaDemotionStore store,
            Material demoteItem,
            Material promoteItem
    ) {
        this.plugin = plugin;
        this.grid = grid;
        this.store = store;
        this.demoteItem = demoteItem;
        this.promoteItem = promoteItem;
    }

    @EventHandler(priority = EventPriority.HIGH, ignoreCancelled = false)
    void onInteract(PlayerInteractEvent event) {
        if (event.getHand() != null && event.getHand() != EquipmentSlot.HAND) {
            return;
        }
        Player player = event.getPlayer();
        if (!player.hasPermission(PERMISSION)) {
            return;
        }
        Block block = event.getClickedBlock();
        if (block == null) {
            return;
        }
        ItemStack held = player.getInventory().getItemInMainHand();
        if (held == null || held.getType() == Material.AIR) {
            return;
        }
        Action action = event.getAction();
        if (action == Action.LEFT_CLICK_BLOCK && held.getType() == demoteItem) {
            if (handleDemote(player, block)) {
                event.setCancelled(true);
            }
        } else if (action == Action.RIGHT_CLICK_BLOCK && held.getType() == promoteItem) {
            if (handlePromote(player, block)) {
                event.setCancelled(true);
            }
        }
    }

    @EventHandler(priority = EventPriority.HIGH, ignoreCancelled = false)
    void onBreak(BlockBreakEvent event) {
        Player player = event.getPlayer();
        if (!player.hasPermission(PERMISSION)) {
            return;
        }
        ItemStack held = player.getInventory().getItemInMainHand();
        if (held == null || held.getType() != demoteItem) {
            return;
        }
        if (handleDemote(player, event.getBlock())) {
            event.setCancelled(true);
        }
    }

    private boolean handleDemote(Player player, Block block) {
        Optional<QaGridIndex.Cell> cell = resolve(player, block);
        if (cell.isEmpty()) {
            return false;
        }
        QaGridIndex.Cell hit = cell.get();
        boolean changed = store.demote(hit.templateId(), player.getName(), hit.gold());
        if (changed) {
            player.sendMessage(Component.text(
                    "Demoted " + hit.templateId() + " (was " + QaDemotionStore.displayWasGold(hit.gold()) + ")",
                    NamedTextColor.GOLD
            ));
            plugin.getLogger().info("[qa-demote] demote " + hit.templateId()
                    + " by " + player.getName() + " was_gold=" + hit.gold());
        } else {
            player.sendMessage(Component.text(
                    "Already demoted " + hit.templateId(),
                    NamedTextColor.YELLOW
            ));
        }
        return true;
    }

    private boolean handlePromote(Player player, Block block) {
        Optional<QaGridIndex.Cell> cell = resolve(player, block);
        if (cell.isEmpty()) {
            return false;
        }
        QaGridIndex.Cell hit = cell.get();
        boolean changed = store.promote(hit.templateId(), player.getName(), hit.gold());
        if (changed) {
            player.sendMessage(Component.text(
                    "Re-promoted " + hit.templateId() + " (cleared demote)",
                    NamedTextColor.GREEN
            ));
            plugin.getLogger().info("[qa-demote] promote " + hit.templateId()
                    + " by " + player.getName());
        } else {
            player.sendMessage(Component.text(
                    "Not demoted: " + hit.templateId(),
                    NamedTextColor.YELLOW
            ));
        }
        return true;
    }

    private Optional<QaGridIndex.Cell> resolve(Player player, Block block) {
        if (!grid.ready()) {
            if (debounceOk(player.getUniqueId())) {
                player.sendMessage(Component.text(
                        "QA grid index not loaded. Copy docs/QA_GRID.json to the plugin folder.",
                        NamedTextColor.RED
                ));
            }
            return Optional.empty();
        }
        Optional<QaGridIndex.Cell> cell = grid.resolve(block.getX(), block.getY(), block.getZ());
        if (cell.isEmpty()) {
            return Optional.empty();
        }
        if (!debounceOk(player.getUniqueId())) {
            return Optional.empty();
        }
        return cell;
    }

    private boolean debounceOk(UUID playerId) {
        long now = System.currentTimeMillis();
        Long previous = debounce.get(playerId);
        if (previous != null && now - previous < DEBOUNCE_MS) {
            return false;
        }
        debounce.put(playerId, now);
        return true;
    }

    static Material materialOr(String raw, Material fallback) {
        if (raw == null || raw.isBlank()) {
            return fallback;
        }
        Material material = Material.matchMaterial(raw.trim());
        return material == null ? fallback : material;
    }
}
