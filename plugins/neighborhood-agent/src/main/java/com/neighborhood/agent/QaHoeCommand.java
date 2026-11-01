package com.neighborhood.agent;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Material;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;
import org.jetbrains.annotations.NotNull;

/**
 * Give any op the QA demote hoe so they can split campus review work.
 */
final class QaHoeCommand implements CommandExecutor {
    private static final String PERMISSION = "neighborhood.agent.qa";

    private final NeighborhoodAgentPlugin plugin;

    QaHoeCommand(NeighborhoodAgentPlugin plugin) {
        this.plugin = plugin;
    }

    @Override
    public boolean onCommand(
            @NotNull CommandSender sender,
            @NotNull Command command,
            @NotNull String label,
            @NotNull String[] args
    ) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage("Only players can use /" + label + ".");
            return true;
        }
        if (!player.hasPermission(PERMISSION)) {
            player.sendMessage(Component.text(
                    "Ops only — ask an operator for neighborhood.agent.qa.",
                    NamedTextColor.RED
            ));
            return true;
        }
        Material item = QaDemoteListener.materialOr(
                plugin.getConfig().getString("qa-demote-item", "WOODEN_HOE"),
                Material.WOODEN_HOE
        );
        ItemStack stack = new ItemStack(item, 1);
        player.getInventory().addItem(stack);
        player.sendMessage(Component.text(
                "QA hoe ready. Left-click a paste to demote, right-click to undo.",
                NamedTextColor.GREEN
        ));
        return true;
    }
}
