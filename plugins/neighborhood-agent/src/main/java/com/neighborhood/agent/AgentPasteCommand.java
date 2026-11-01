package com.neighborhood.agent;

import com.google.gson.JsonObject;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.jetbrains.annotations.NotNull;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Console/RCON-only force-paste for template QA grids.
 *
 * <pre>
 * agent-paste-at &lt;world&gt; &lt;x&gt; &lt;y&gt; &lt;z&gt; &lt;template_id&gt;
 * agent-paste &lt;player&gt; &lt;template_id&gt;   (legacy; requires online player)
 * </pre>
 *
 * Prefer {@code agent-paste-at} — it never teleports or touches a player.
 * Writes {@code qa_last_paste.json} under the plugin data folder for harness polling.
 */
public final class AgentPasteCommand implements CommandExecutor {
    private static final AtomicLong SEQUENCE = new AtomicLong();

    private final NeighborhoodAgentPlugin plugin;
    private final CompanionGateway gateway;

    public AgentPasteCommand(NeighborhoodAgentPlugin plugin, CompanionGateway gateway) {
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
                    "agent-paste is console/RCON only.",
                    NamedTextColor.RED
            ));
            return true;
        }
        String name = command.getName().equalsIgnoreCase("agent-paste-at")
                || label.equalsIgnoreCase("agent-paste-at")
                ? "agent-paste-at"
                : "agent-paste";
        if ("agent-paste-at".equals(name)) {
            return pasteAt(sender, args);
        }
        return pasteAsPlayer(sender, args);
    }

    private boolean pasteAt(CommandSender sender, String[] args) {
        if (args.length != 5) {
            sender.sendMessage("Usage: agent-paste-at <world> <x> <y> <z> <template_id>");
            return true;
        }
        String worldName = args[0];
        World world = Bukkit.getWorld(worldName);
        if (world == null) {
            sender.sendMessage("[agent-paste-at] FAIL unknown world: " + worldName);
            writeStatus(0L, args[4], false, false, "unknown world");
            return true;
        }
        final int x;
        final int y;
        final int z;
        try {
            x = Integer.parseInt(args[1]);
            y = Integer.parseInt(args[2]);
            z = Integer.parseInt(args[3]);
        } catch (NumberFormatException error) {
            sender.sendMessage("Usage: agent-paste-at <world> <x> <y> <z> <template_id>");
            return true;
        }
        String templateId = args[4].trim().toLowerCase();
        long seq = SEQUENCE.incrementAndGet();
        writeStatus(seq, templateId, false, false, "submitted");
        sender.sendMessage(
                "[agent-paste-at] SUBMITTED " + templateId
                        + " @ " + worldName + " " + x + "," + y + "," + z
        );
        plugin.getLogger().info(
                "[agent-paste-at] submit template_id=" + templateId
                        + " world=" + worldName + " stand=" + x + "," + y + "," + z
                        + " seq=" + seq
        );

        gateway.forcePasteTemplateAt(worldName, x, y, z, templateId).whenComplete(
                (result, throwable) -> plugin.getServer().getScheduler().runTask(plugin, () -> {
                    boolean executed = throwable == null && result != null && result.executed();
                    boolean verified = result != null && result.verified();
                    String message = throwable != null
                            ? String.valueOf(throwable.getMessage())
                            : (result != null ? result.message() : "no result");
                    writeStatus(seq, templateId, executed, verified, message == null ? "" : message);
                    String line = "[agent-paste-at] "
                            + (executed ? "OK" : "FAIL")
                            + " seq=" + seq
                            + " template_id=" + templateId
                            + " verified=" + verified
                            + " message=" + message;
                    plugin.getLogger().info(line);
                    Bukkit.getConsoleSender().sendMessage(line);
                })
        );
        return true;
    }

    private boolean pasteAsPlayer(CommandSender sender, String[] args) {
        if (args.length != 2) {
            sender.sendMessage(
                    "Usage: agent-paste-at <world> <x> <y> <z> <template_id>"
                            + "  OR  agent-paste <player> <template_id> (legacy)"
            );
            return true;
        }

        String playerName = args[0];
        String templateId = args[1].trim().toLowerCase();
        Player player = Bukkit.getPlayerExact(playerName);
        if (player == null) {
            for (Player online : Bukkit.getOnlinePlayers()) {
                if (online.getName().equalsIgnoreCase(playerName)) {
                    player = online;
                    break;
                }
            }
        }
        if (player == null) {
            sender.sendMessage("[agent-paste] FAIL player offline: " + playerName
                    + " — use agent-paste-at <world> <x> <y> <z> <template_id>");
            writeStatus(0L, templateId, false, false, "player offline");
            return true;
        }

        long seq = SEQUENCE.incrementAndGet();
        writeStatus(seq, templateId, false, false, "submitted");
        sender.sendMessage("[agent-paste] SUBMITTED " + player.getName() + " :: " + templateId);
        plugin.getLogger().info("[agent-paste] submit player=" + player.getName()
                + " template_id=" + templateId + " seq=" + seq);

        Player target = player;
        gateway.forcePasteTemplate(target, templateId).whenComplete((result, throwable) ->
                plugin.getServer().getScheduler().runTask(plugin, () -> {
                    boolean executed = throwable == null && result != null && result.executed();
                    boolean verified = result != null && result.verified();
                    String message = throwable != null
                            ? String.valueOf(throwable.getMessage())
                            : (result != null ? result.message() : "no result");
                    writeStatus(seq, templateId, executed, verified, message == null ? "" : message);
                    String line = "[agent-paste] "
                            + (executed ? "OK" : "FAIL")
                            + " seq=" + seq
                            + " template_id=" + templateId
                            + " verified=" + verified
                            + " message=" + message;
                    plugin.getLogger().info(line);
                    Bukkit.getConsoleSender().sendMessage(line);
                }));
        return true;
    }

    private void writeStatus(
            long seq,
            String templateId,
            boolean ok,
            boolean verified,
            String message
    ) {
        JsonObject json = new JsonObject();
        json.addProperty("seq", seq);
        json.addProperty("template_id", templateId);
        json.addProperty("ok", ok);
        json.addProperty("verified", verified);
        json.addProperty("done", !"submitted".equals(message));
        json.addProperty("message", message == null ? "" : message);
        json.addProperty("updated_ms", System.currentTimeMillis());
        Path path = plugin.getDataFolder().toPath().resolve("qa_last_paste.json");
        try {
            Files.createDirectories(path.getParent());
            Files.writeString(path, json.toString(), StandardCharsets.UTF_8);
        } catch (IOException error) {
            plugin.getLogger().warning("Could not write qa_last_paste.json: " + error.getMessage());
        }
    }
}
