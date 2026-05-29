package com.neighborhood.agent;

import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.jetbrains.annotations.NotNull;

/**
 * Console-only command used by the orchestrator to dispatch a Bukkit command
 * <strong>as the actual {@link Player} object</strong>. This is required for
 * FAWE/WorldEdit because {@code execute as &lt;player&gt; at @s run /sphere ...}
 * still executes with a non-player {@code CommandSender}, and FAWE then has no
 * world/extent and throws NPEs. {@code Player.performCommand} runs through the
 * normal Bukkit command pipeline with the real player as sender, so FAWE gets
 * a valid LocalSession.
 *
 * Refuses any in-game caller — only console (RCON) can invoke it.
 */
public final class AgentExecCommand implements CommandExecutor {

    private final NeighborhoodAgentPlugin plugin;

    public AgentExecCommand(NeighborhoodAgentPlugin plugin) {
        this.plugin = plugin;
    }

    @Override
    public boolean onCommand(
            @NotNull CommandSender sender,
            @NotNull Command command,
            @NotNull String label,
            @NotNull String[] args
    ) {
        if (sender instanceof Player) {
            sender.sendMessage("ERROR: /agentexec is console-only");
            return true;
        }
        if (args.length < 2) {
            sender.sendMessage("Usage: /agentexec <player> <command...>");
            return true;
        }

        String playerName = args[0];
        Player target = plugin.getServer().getPlayerExact(playerName);
        if (target == null) {
            sender.sendMessage("ERROR: player not online: " + playerName);
            return true;
        }

        StringBuilder sb = new StringBuilder();
        for (int i = 1; i < args.length; i++) {
            if (i > 1) sb.append(' ');
            sb.append(args[i]);
        }
        // performCommand strips exactly ONE leading '/' before dispatch. FAWE's
        // canonical command name is literally "/sphere" (with the slash baked
        // in), which is why players type "//sphere ..." in chat — only the
        // first '/' is the chat prefix. So we strip exactly one leading slash
        // here: "//sphere glass 4" -> "/sphere glass 4" -> performCommand
        // dispatches "//sphere glass 4". A bare "sphere" (no slash) becomes
        // "sphere" -> "/sphere", which Paper aliases to FAWE without proper
        // session injection.
        String raw = sb.toString().trim();
        if (raw.startsWith("/")) {
            raw = raw.substring(1);
        }
        if (raw.isEmpty()) {
            sender.sendMessage("ERROR: empty command");
            return true;
        }
        final String dispatch = raw;

        // Bukkit commands must run on the main thread; FAWE itself queues
        // async work after that. We acknowledge dispatch synchronously to RCON.
        plugin.getServer().getScheduler().runTask(plugin, () -> {
            try {
                target.performCommand(dispatch);
            } catch (Throwable t) {
                plugin.getLogger().warning(
                        "agentexec dispatch failed for " + target.getName()
                                + " /" + dispatch + ": " + t.getMessage());
            }
        });

        sender.sendMessage("OK: dispatched /" + dispatch + " as " + target.getName());
        return true;
    }
}
