package com.neighborhood.agent;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** `/builds` — open the Build Book GUI or give the book item. */
public final class BuildsCommand implements CommandExecutor, TabCompleter {

    private final BuildBrowser browser;
    private final String displayName;

    public BuildsCommand(BuildBrowser browser, String displayName) {
        this.browser = browser;
        this.displayName = displayName;
    }

    @Override
    public boolean onCommand(
            @NotNull CommandSender sender,
            @NotNull Command command,
            @NotNull String label,
            @NotNull String[] args
    ) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(Component.text(
                    "Only players can use /builds.",
                    NamedTextColor.RED
            ));
            return true;
        }
        if (!player.hasPermission("neighborhood.agent")) {
            player.sendMessage(Component.text(
                    "You can't use " + displayName + " here. Try: ask a grown-up for help.",
                    NamedTextColor.RED
            ));
            return true;
        }
        if (args.length >= 1) {
            String sub = args[0].toLowerCase(Locale.ROOT);
            if (sub.equals("book") || sub.equals("item")) {
                browser.bookItem().give(player);
                return true;
            }
            if (sub.equals("help") || sub.equals("?")) {
                player.sendMessage(Component.text(
                        "/" + label + " — open the Build Book",
                        NamedTextColor.AQUA
                ));
                player.sendMessage(Component.text(
                        "/" + label + " book — get the book item",
                        NamedTextColor.GRAY
                ));
                return true;
            }
        }
        browser.openHome(player);
        return true;
    }

    @Override
    public @Nullable List<String> onTabComplete(
            @NotNull CommandSender sender,
            @NotNull Command command,
            @NotNull String alias,
            @NotNull String[] args
    ) {
        if (args.length == 1) {
            String prefix = args[0].toLowerCase(Locale.ROOT);
            List<String> out = new ArrayList<>();
            for (String option : List.of("book", "help")) {
                if (option.startsWith(prefix)) {
                    out.add(option);
                }
            }
            return out;
        }
        return List.of();
    }
}
