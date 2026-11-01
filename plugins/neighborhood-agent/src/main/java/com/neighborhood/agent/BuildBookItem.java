package com.neighborhood.agent;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Material;
import org.bukkit.NamespacedKey;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.persistence.PersistentDataType;
import org.bukkit.plugin.java.JavaPlugin;

import java.util.List;

/** PDC-tagged book that opens the Build Book GUI on right-click. */
final class BuildBookItem {

    private final NamespacedKey key;
    private final String displayName;

    BuildBookItem(JavaPlugin plugin, String displayName) {
        this.key = new NamespacedKey(plugin, "crafter_build_book");
        this.displayName = displayName == null || displayName.isBlank() ? "Crafter" : displayName.trim();
    }

    NamespacedKey key() {
        return key;
    }

    boolean isBuildBook(ItemStack stack) {
        if (stack == null || stack.getType().isAir() || !stack.hasItemMeta()) {
            return false;
        }
        Byte marker = stack.getItemMeta().getPersistentDataContainer().get(key, PersistentDataType.BYTE);
        return marker != null && marker == (byte) 1;
    }

    ItemStack create() {
        ItemStack stack = new ItemStack(Material.BOOK);
        ItemMeta meta = stack.getItemMeta();
        meta.displayName(
                Component.text(displayName + "'s Build Book", NamedTextColor.AQUA)
                        .decoration(TextDecoration.ITALIC, false)
        );
        meta.lore(List.of(
                Component.text("Right-click to browse builds", NamedTextColor.GRAY)
                        .decoration(TextDecoration.ITALIC, false),
                Component.text("Pick a build → paste near you", NamedTextColor.DARK_GRAY)
                        .decoration(TextDecoration.ITALIC, false)
        ));
        meta.getPersistentDataContainer().set(key, PersistentDataType.BYTE, (byte) 1);
        stack.setItemMeta(meta);
        return stack;
    }

    void give(Player player) {
        player.getInventory().addItem(create());
        player.sendMessage(Component.text(
                "[" + displayName + "] ",
                NamedTextColor.DARK_AQUA
        ).append(Component.text(
                "Here's your Build Book — right-click it anytime!",
                NamedTextColor.GREEN
        )));
    }
}
