package com.neighborhood.agent;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
import org.bukkit.Material;
import org.bukkit.NamespacedKey;
import org.bukkit.entity.Player;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.InventoryHolder;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.persistence.PersistentDataType;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * Chest GUI for browsing gold templates and confirming paste.
 */
final class BuildBrowser {

    static final int PAGE_SIZE = 28;

    enum Screen {
        HOME,
        LIST,
        CONFIRM,
        CLEAR_CONFIRM
    }

    /** Marker holder so click listener can recognize our inventories. */
    static final class Holder implements InventoryHolder {
        final Screen screen;
        final TemplateCatalog.Bucket bucket;
        final String filter;
        final int page;
        final String templateId;
        final boolean needsClear;

        Holder(
                Screen screen,
                TemplateCatalog.Bucket bucket,
                String filter,
                int page,
                String templateId,
                boolean needsClear
        ) {
            this.screen = screen;
            this.bucket = bucket;
            this.filter = filter == null ? "" : filter;
            this.page = Math.max(1, page);
            this.templateId = templateId;
            this.needsClear = needsClear;
        }

        @Override
        public Inventory getInventory() {
            return null;
        }
    }

    private final NeighborhoodAgentPlugin plugin;
    private final CompanionGateway gateway;
    private final BuildBookItem bookItem;
    private final BuildBrowserSessions sessions;
    private final NamespacedKey templateIdKey;
    private final String displayName;

    BuildBrowser(
            NeighborhoodAgentPlugin plugin,
            CompanionGateway gateway,
            BuildBookItem bookItem,
            BuildBrowserSessions sessions
    ) {
        this.plugin = plugin;
        this.gateway = gateway;
        this.bookItem = bookItem;
        this.sessions = sessions;
        this.templateIdKey = new NamespacedKey(plugin, "browse_template_id");
        this.displayName = plugin.getDisplayName();
    }

    BuildBrowserSessions sessions() {
        return sessions;
    }

    BuildBookItem bookItem() {
        return bookItem;
    }

    TemplateCatalog catalog() {
        TemplateCatalog current = gateway.templateCatalog();
        TemplateCatalog refreshed = current.refreshIfStale();
        if (refreshed != current) {
            gateway.replaceTemplateCatalog(refreshed);
        }
        return refreshed;
    }

    void openHome(Player player) {
        sessions.clear(player.getUniqueId());
        Holder holder = new Holder(Screen.HOME, null, "", 1, null, false);
        Inventory inv = Bukkit.createInventory(holder, 27, Component.text(displayName + " Builds"));
        set(inv, 10, categoryIcon(TemplateCatalog.Bucket.HOUSES, Material.OAK_DOOR));
        set(inv, 11, categoryIcon(TemplateCatalog.Bucket.FARMS, Material.HAY_BLOCK));
        set(inv, 12, categoryIcon(TemplateCatalog.Bucket.FORTS, Material.STONE_BRICKS));
        set(inv, 13, categoryIcon(TemplateCatalog.Bucket.BRIDGES, Material.OAK_PLANKS));
        set(inv, 14, categoryIcon(TemplateCatalog.Bucket.PARKS, Material.POPPY));
        set(inv, 15, categoryIcon(TemplateCatalog.Bucket.NATURE, Material.OAK_SAPLING));
        set(inv, 16, categoryIcon(TemplateCatalog.Bucket.UTILITY, Material.CRAFTING_TABLE));
        set(inv, 20, named(Material.BOOKSHELF, "All builds", NamedTextColor.GOLD,
                List.of("Show every ready-made build")));
        set(inv, 22, named(Material.COMPASS, "Search", NamedTextColor.AQUA,
                List.of("Type a word in chat", "Example: coop · castle · farm")));
        set(inv, 24, named(Material.BOOK, "Get Build Book", NamedTextColor.GREEN,
                List.of("Put the book in your inventory")));
        set(inv, 26, named(Material.BARRIER, "Close", NamedTextColor.RED, List.of()));
        player.openInventory(inv);
    }

    void openList(Player player, TemplateCatalog.Bucket bucket, String filter, int page) {
        TemplateCatalog catalog = catalog();
        List<TemplateCatalog.Entry> entries = catalog.search(filter, bucket);
        int totalPages = Math.max(1, (entries.size() + PAGE_SIZE - 1) / PAGE_SIZE);
        int safePage = Math.min(Math.max(1, page), totalPages);
        int start = (safePage - 1) * PAGE_SIZE;
        int end = Math.min(start + PAGE_SIZE, entries.size());

        String title;
        if (filter != null && !filter.isBlank()) {
            title = "Search: " + clip(filter, 20);
        } else if (bucket != null) {
            title = bucket.label;
        } else {
            title = "All builds";
        }
        Holder holder = new Holder(Screen.LIST, bucket, filter, safePage, null, false);
        Inventory inv = Bukkit.createInventory(holder, 54, Component.text(title));

        int slot = 0;
        for (int i = start; i < end; i++) {
            inv.setItem(slot++, buildIcon(entries.get(i)));
        }

        set(inv, 45, named(Material.ARROW, "Back", NamedTextColor.YELLOW, List.of("Categories")));
        if (safePage > 1) {
            set(inv, 48, named(Material.SPECTRAL_ARROW, "Previous page", NamedTextColor.AQUA,
                    List.of("Page " + (safePage - 1))));
        }
        set(inv, 49, named(Material.PAPER, "Page " + safePage + "/" + totalPages, NamedTextColor.WHITE,
                List.of(entries.size() + " build" + (entries.size() == 1 ? "" : "s"))));
        if (safePage < totalPages) {
            set(inv, 50, named(Material.SPECTRAL_ARROW, "Next page", NamedTextColor.AQUA,
                    List.of("Page " + (safePage + 1))));
        }
        if (filter != null && !filter.isBlank()) {
            set(inv, 52, named(Material.MILK_BUCKET, "Clear search", NamedTextColor.GOLD,
                    List.of("Show all in this group")));
        }
        set(inv, 53, named(Material.COMPASS, "New search", NamedTextColor.AQUA,
                List.of("Type another word in chat")));
        player.openInventory(inv);
    }

    void openConfirm(Player player, String templateId, boolean needsClear) {
        TemplateCatalog.Entry entry = catalog().entry(templateId);
        if (entry == null || !entry.gold()) {
            player.sendMessage(prefix().append(Component.text(
                    "That build isn't in the book.",
                    NamedTextColor.RED
            )));
            openHome(player);
            return;
        }
        Screen screen = needsClear ? Screen.CLEAR_CONFIRM : Screen.CONFIRM;
        Holder holder = new Holder(screen, entry.bucket(), "", 1, templateId, needsClear);
        String heading = needsClear ? "Clear & paste?" : "Paste here?";
        Inventory inv = Bukkit.createInventory(holder, 27, Component.text(heading));
        set(inv, 13, buildIcon(entry));
        if (needsClear) {
            set(inv, 11, named(Material.IRON_SHOVEL, "Yes — clear & paste", NamedTextColor.GOLD,
                    List.of("Clear the spot, then paste", entry.title())));
        } else {
            set(inv, 11, named(Material.LIME_CONCRETE, "Paste here", NamedTextColor.GREEN,
                    List.of(
                            "Build " + TemplateCatalog.withArticle(entry.title()),
                            "near where you stand"
                    )));
        }
        set(inv, 15, named(Material.RED_CONCRETE, "Cancel", NamedTextColor.RED, List.of("Go back")));
        player.openInventory(inv);
    }

    void beginSearch(Player player, TemplateCatalog.Bucket bucket, String filter, int page) {
        player.closeInventory();
        sessions.put(
                player.getUniqueId(),
                BuildBrowserSessions.Session.search(bucket, filter, page)
        );
        player.sendMessage(prefix().append(Component.text(
                "Type a search word in chat (or cancel).",
                NamedTextColor.YELLOW
        )));
    }

    void paste(Player player, String templateId, boolean clearSite) {
        if (!player.hasPermission("neighborhood.agent.build")) {
            player.sendMessage(prefix().append(Component.text(
                    "I can't build here. Try: ask a grown-up for help.",
                    NamedTextColor.RED
            )));
            return;
        }
        player.closeInventory();
        String title = catalog().titleFor(templateId);
        player.sendMessage(prefix().append(Component.text(
                "Pasting " + TemplateCatalog.withArticle(title) + "…",
                NamedTextColor.AQUA
        )));
        gateway.pasteFromBrowser(player, templateId, clearSite).whenComplete((result, error) ->
                plugin.getServer().getScheduler().runTask(plugin, () -> {
                    if (error != null) {
                        player.sendMessage(prefix().append(Component.text(
                                "I couldn't paste that safely.",
                                NamedTextColor.RED
                        )));
                        return;
                    }
                    if (result == null) {
                        return;
                    }
                    if (!result.ok() && isNeedsClear(result.message())) {
                        openConfirm(player, templateId, true);
                        return;
                    }
                    NamedTextColor color = result.ok() ? NamedTextColor.GREEN : NamedTextColor.RED;
                    player.sendMessage(prefix().append(Component.text(result.message(), color)));
                }));
    }

    String templateIdFrom(ItemStack stack) {
        if (stack == null || !stack.hasItemMeta()) {
            return null;
        }
        return stack.getItemMeta().getPersistentDataContainer().get(
                templateIdKey,
                PersistentDataType.STRING
        );
    }

    private Component prefix() {
        return Component.text("[" + displayName + "] ", NamedTextColor.DARK_AQUA);
    }

    private static boolean isNeedsClear(String message) {
        if (message == null) {
            return false;
        }
        if (message.equals(SchematicPlacement.CLEAR_ASK_MESSAGE)) {
            return true;
        }
        String lower = message.toLowerCase(Locale.ROOT);
        return lower.contains("clear") && lower.contains("ground");
    }

    private ItemStack categoryIcon(TemplateCatalog.Bucket bucket, Material material) {
        int count = catalog().byBucket(bucket).size();
        return named(
                material,
                bucket.label,
                NamedTextColor.AQUA,
                List.of(count + " build" + (count == 1 ? "" : "s"), "Click to browse")
        );
    }

    private ItemStack buildIcon(TemplateCatalog.Entry entry) {
        Material material = iconFor(entry);
        int[] fp = entry.footprint();
        List<String> lore = new ArrayList<>();
        if (fp[0] > 0 && fp[1] > 0 && fp[2] > 0) {
            lore.add("Size: " + fp[0] + "×" + fp[1] + "×" + fp[2]);
        }
        if (entry.maxBlocks() > 0) {
            lore.add("~" + entry.maxBlocks() + " blocks");
        }
        if (entry.complexity() != null && !entry.complexity().isBlank()) {
            lore.add(capitalize(entry.complexity()));
        }
        lore.add("Click to paste near you");
        ItemStack stack = named(material, entry.title(), NamedTextColor.GREEN, lore);
        ItemMeta meta = stack.getItemMeta();
        meta.getPersistentDataContainer().set(templateIdKey, PersistentDataType.STRING, entry.id());
        stack.setItemMeta(meta);
        return stack;
    }

    private static Material iconFor(TemplateCatalog.Entry entry) {
        TemplateCatalog.Bucket bucket = entry.bucket();
        if (bucket == null) {
            return Material.BRICKS;
        }
        return switch (bucket) {
            case HOUSES -> Material.BRICKS;
            case FARMS -> Material.WHEAT;
            case FORTS -> Material.IRON_BARS;
            case BRIDGES -> Material.OAK_STAIRS;
            case PARKS -> Material.MOSS_BLOCK;
            case NATURE -> Material.OAK_LEAVES;
            case UTILITY -> Material.SMITHING_TABLE;
        };
    }

    private static ItemStack named(
            Material material,
            String name,
            NamedTextColor color,
            List<String> loreLines
    ) {
        ItemStack stack = new ItemStack(material);
        ItemMeta meta = stack.getItemMeta();
        meta.displayName(Component.text(name, color).decoration(TextDecoration.ITALIC, false));
        if (loreLines != null && !loreLines.isEmpty()) {
            List<Component> lore = new ArrayList<>();
            for (String line : loreLines) {
                lore.add(Component.text(line, NamedTextColor.GRAY).decoration(TextDecoration.ITALIC, false));
            }
            meta.lore(lore);
        }
        stack.setItemMeta(meta);
        return stack;
    }

    private static void set(Inventory inv, int slot, ItemStack stack) {
        inv.setItem(slot, stack);
    }

    private static String clip(String text, int max) {
        if (text.length() <= max) {
            return text;
        }
        return text.substring(0, max - 1) + "…";
    }

    private static String capitalize(String raw) {
        if (raw == null || raw.isEmpty()) {
            return "";
        }
        return Character.toUpperCase(raw.charAt(0)) + raw.substring(1).toLowerCase(Locale.ROOT);
    }
}
