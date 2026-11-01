package com.neighborhood.agent;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Material;
import org.bukkit.block.Block;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.block.BlockPlaceEvent;
import org.bukkit.event.player.PlayerBucketEmptyEvent;

/**
 * Blocks players from placing lava or emptying lava buckets.
 * Bypass with {@code neighborhood.lava.place} (ops by default).
 */
final class LavaGuardListener implements Listener {
    private static final String BYPASS = "neighborhood.lava.place";

    @EventHandler(priority = EventPriority.HIGH, ignoreCancelled = true)
    void onBucketEmpty(PlayerBucketEmptyEvent event) {
        if (event.getBucket() != Material.LAVA_BUCKET) {
            return;
        }
        if (event.getPlayer().hasPermission(BYPASS)) {
            return;
        }
        event.setCancelled(true);
        event.getPlayer().sendMessage(
                Component.text("Lava isn't allowed here.", NamedTextColor.RED)
        );
    }

    @EventHandler(priority = EventPriority.HIGH, ignoreCancelled = true)
    void onBlockPlace(BlockPlaceEvent event) {
        Block block = event.getBlockPlaced();
        if (block.getType() != Material.LAVA) {
            return;
        }
        if (event.getPlayer().hasPermission(BYPASS)) {
            return;
        }
        event.setCancelled(true);
        event.getPlayer().sendMessage(
                Component.text("Lava isn't allowed here.", NamedTextColor.RED)
        );
    }
}
