package com.neighborhood.agent;

import io.papermc.paper.event.player.AsyncChatEvent;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.serializer.plain.PlainTextComponentSerializer;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.block.Action;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.inventory.InventoryDragEvent;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.EquipmentSlot;

import java.util.Locale;

/**
 * Build Book GUI clicks, book right-click, and chat search filter.
 */
final class BuildBrowserListener implements Listener {

    private final NeighborhoodAgentPlugin plugin;
    private final BuildBrowser browser;
    private final String displayName;

    BuildBrowserListener(
            NeighborhoodAgentPlugin plugin,
            BuildBrowser browser,
            String displayName
    ) {
        this.plugin = plugin;
        this.browser = browser;
        this.displayName = displayName;
    }

    @EventHandler(priority = EventPriority.HIGH, ignoreCancelled = true)
    void onInventoryClick(InventoryClickEvent event) {
        Inventory top = event.getView().getTopInventory();
        if (!(top.getHolder() instanceof BuildBrowser.Holder holder)) {
            return;
        }
        event.setCancelled(true);
        if (!(event.getWhoClicked() instanceof Player player)) {
            return;
        }
        if (event.getClickedInventory() == null || event.getClickedInventory() != top) {
            return;
        }
        ItemStack clicked = event.getCurrentItem();
        if (clicked == null || clicked.getType().isAir()) {
            return;
        }
        switch (holder.screen) {
            case HOME -> handleHome(player, event.getSlot());
            case LIST -> handleList(player, holder, event.getSlot(), clicked);
            case CONFIRM, CLEAR_CONFIRM -> handleConfirm(player, holder, event.getSlot());
        }
    }

    @EventHandler(priority = EventPriority.HIGH, ignoreCancelled = true)
    void onInventoryDrag(InventoryDragEvent event) {
        if (event.getView().getTopInventory().getHolder() instanceof BuildBrowser.Holder) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGH, ignoreCancelled = true)
    void onBookUse(PlayerInteractEvent event) {
        if (event.getHand() != EquipmentSlot.HAND) {
            return;
        }
        Action action = event.getAction();
        if (action != Action.RIGHT_CLICK_AIR && action != Action.RIGHT_CLICK_BLOCK) {
            return;
        }
        ItemStack item = event.getItem();
        if (!browser.bookItem().isBuildBook(item)) {
            return;
        }
        event.setCancelled(true);
        Player player = event.getPlayer();
        if (!player.hasPermission("neighborhood.agent")) {
            return;
        }
        browser.openHome(player);
    }

    @EventHandler(priority = EventPriority.LOWEST, ignoreCancelled = false)
    void onSearchChat(AsyncChatEvent event) {
        Player player = event.getPlayer();
        BuildBrowserSessions.Session session = browser.sessions().get(player.getUniqueId());
        if (session == null || session.mode() != BuildBrowserSessions.Mode.SEARCH_CHAT) {
            return;
        }
        event.setCancelled(true);
        event.viewers().clear();
        String text = PlainTextComponentSerializer.plainText().serialize(event.message()).trim();
        browser.sessions().clear(player.getUniqueId());
        plugin.getServer().getScheduler().runTask(
                plugin,
                () -> handleSearchLine(player, session, text)
        );
    }

    private void handleSearchLine(
            Player player,
            BuildBrowserSessions.Session session,
            String text
    ) {
        String lower = text.toLowerCase(Locale.ROOT);
        if (lower.isEmpty() || lower.equals("cancel") || lower.equals("never mind")
                || lower.equals("stop")) {
            player.sendMessage(Component.text(
                    "[" + displayName + "] ",
                    NamedTextColor.DARK_AQUA
            ).append(Component.text("Search cancelled.", NamedTextColor.GRAY)));
            browser.openList(player, session.bucket(), session.filter(), session.page());
            return;
        }
        browser.openList(player, session.bucket(), text, 1);
    }

    private void handleHome(Player player, int slot) {
        switch (slot) {
            case 10 -> browser.openList(player, TemplateCatalog.Bucket.HOUSES, "", 1);
            case 11 -> browser.openList(player, TemplateCatalog.Bucket.FARMS, "", 1);
            case 12 -> browser.openList(player, TemplateCatalog.Bucket.FORTS, "", 1);
            case 13 -> browser.openList(player, TemplateCatalog.Bucket.BRIDGES, "", 1);
            case 14 -> browser.openList(player, TemplateCatalog.Bucket.PARKS, "", 1);
            case 15 -> browser.openList(player, TemplateCatalog.Bucket.NATURE, "", 1);
            case 16 -> browser.openList(player, TemplateCatalog.Bucket.UTILITY, "", 1);
            case 20 -> browser.openList(player, null, "", 1);
            case 22 -> browser.beginSearch(player, null, "", 1);
            case 24 -> browser.bookItem().give(player);
            case 26 -> player.closeInventory();
            default -> {
            }
        }
    }

    private void handleList(
            Player player,
            BuildBrowser.Holder holder,
            int slot,
            ItemStack clicked
    ) {
        if (slot == 45) {
            browser.openHome(player);
            return;
        }
        if (slot == 48 && holder.page > 1) {
            browser.openList(player, holder.bucket, holder.filter, holder.page - 1);
            return;
        }
        if (slot == 50) {
            browser.openList(player, holder.bucket, holder.filter, holder.page + 1);
            return;
        }
        if (slot == 52) {
            browser.openList(player, holder.bucket, "", 1);
            return;
        }
        if (slot == 53) {
            browser.beginSearch(player, holder.bucket, holder.filter, holder.page);
            return;
        }
        if (slot >= BuildBrowser.PAGE_SIZE) {
            return;
        }
        String templateId = browser.templateIdFrom(clicked);
        if (templateId == null || templateId.isBlank()) {
            return;
        }
        browser.openConfirm(player, templateId, false);
    }

    private void handleConfirm(Player player, BuildBrowser.Holder holder, int slot) {
        if (slot == 15) {
            if (holder.bucket != null) {
                browser.openList(player, holder.bucket, "", 1);
            } else {
                browser.openHome(player);
            }
            return;
        }
        if (slot != 11 || holder.templateId == null) {
            return;
        }
        // "Paste here" is consent to clear the pad — no second clear confirm.
        browser.paste(player, holder.templateId, true);
    }
}
