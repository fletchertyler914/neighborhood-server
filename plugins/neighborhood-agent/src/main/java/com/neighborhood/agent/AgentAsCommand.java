package com.neighborhood.agent;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Bukkit;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.jetbrains.annotations.NotNull;

/**
 * Console/RCON-only hook for live validation.
 *
 * <pre>agent-as &lt;player&gt; &lt;prompt...&gt;</pre>
 *
 * Runs the real companion job path as the named online player so harnesses
 * can drive /agent (or /ai) without typing in chat.
 */
public final class AgentAsCommand implements CommandExecutor {
    private final NeighborhoodAgentPlugin plugin;
    private final CompanionGateway gateway;

    public AgentAsCommand(NeighborhoodAgentPlugin plugin, CompanionGateway gateway) {
        this.plugin = plugin;
        this.gateway = gateway;
    }

    @Override
    public boolean onCommand(
            @NotNull CommandSender sender,
            @NotNull Command command,
            @NotNull String label,
            @NotNull String[] args
    ) {
        if (sender instanceof Player) {
            sender.sendMessage(Component.text(
                    "agent-as is console/RCON only. Players should use /agent or /ai.",
                    NamedTextColor.RED
            ));
            return true;
        }
        if (args.length < 2) {
            sender.sendMessage("Usage: agent-as <player> <prompt...>");
            return true;
        }
        if (!gateway.isReady()) {
            sender.sendMessage("[agent-as] FAIL gateway offline");
            plugin.getLogger().warning("[agent-as] gateway offline");
            return true;
        }

        String playerName = args[0];
        Player player = Bukkit.getPlayerExact(playerName);
        if (player == null) {
            // Floodgate names keep their leading '.' — also try case-insensitive scan.
            for (Player online : Bukkit.getOnlinePlayers()) {
                if (online.getName().equalsIgnoreCase(playerName)) {
                    player = online;
                    break;
                }
            }
        }
        if (player == null) {
            sender.sendMessage("[agent-as] FAIL player offline: " + playerName);
            plugin.getLogger().warning("[agent-as] player offline: " + playerName);
            return true;
        }

        String prompt = String.join(" ", java.util.Arrays.copyOfRange(args, 1, args.length));
        CompanionGateway.JobPayload payload = CompanionGateway.JobPayload.from(
                player,
                prompt,
                gateway.perception()
        );
        plugin.getLogger().info("[agent-as] submit player=" + player.getName() + " prompt=" + prompt);
        sender.sendMessage("[agent-as] SUBMITTED " + player.getName() + " :: " + prompt);

        Player target = player;
        gateway.submitJob(payload).whenComplete((result, throwable) ->
                plugin.getServer().getScheduler().runTask(plugin, () -> {
                    boolean ok = throwable == null && result != null && result.ok();
                    String message = throwable != null
                            ? throwable.getMessage()
                            : (result != null ? result.message() : "no result");
                    boolean verified = result != null && result.verified();
                    int totalMs = result != null ? result.totalMs() : -1;
                    String line = "[agent-as] "
                            + (ok ? "OK" : "FAIL")
                            + " verified=" + verified
                            + " total_ms=" + totalMs
                            + " message=" + message;
                    plugin.getLogger().info(line);
                    Bukkit.getConsoleSender().sendMessage(line);
                    if (target.isOnline()) {
                        NamedTextColor color = ok ? NamedTextColor.GREEN : NamedTextColor.RED;
                        String name = plugin.getDisplayName();
                        target.sendMessage(Component.text("[" + name + "] ", NamedTextColor.DARK_AQUA)
                                .append(Component.text(message == null ? "" : message, color)));
                    }
                }));
        return true;
    }
}
