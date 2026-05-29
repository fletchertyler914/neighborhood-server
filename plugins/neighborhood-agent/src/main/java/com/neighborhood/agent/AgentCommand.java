package com.neighborhood.agent;

import net.kyori.adventure.bossbar.BossBar;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.GameMode;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;
import org.bukkit.scheduler.BukkitTask;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.util.ArrayList;
import java.util.List;

public final class AgentCommand implements CommandExecutor, TabCompleter {

    private final NeighborhoodAgentPlugin plugin;
    private final OrchestratorClient orchestrator;

    public AgentCommand(NeighborhoodAgentPlugin plugin, OrchestratorClient orchestrator) {
        this.plugin = plugin;
        this.orchestrator = orchestrator;
    }

    @Override
    public boolean onCommand(
            @NotNull CommandSender sender,
            @NotNull Command command,
            @NotNull String label,
            @NotNull String[] args
    ) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(Component.text("Only players can use /agent.", NamedTextColor.RED));
            return true;
        }
        if (!player.hasPermission("neighborhood.agent")) {
            player.sendMessage(Component.text("You don't have permission.", NamedTextColor.RED));
            return true;
        }
        if (args.length == 0) {
            player.sendMessage(Component.text("Usage: /agent <prompt>", NamedTextColor.YELLOW));
            player.sendMessage(
                    Component.text("Example: /agent build a 21x21 quartz platform at my feet", NamedTextColor.GRAY)
            );
            return true;
        }

        String prompt = String.join(" ", args);
        var loc = player.getLocation();
        String world = player.getWorld().getKey().toString();
        GameMode gm = player.getGameMode();
        String gamemode = gm.name().toLowerCase();

        long startMs = System.currentTimeMillis();
        String shortPrompt = prompt.length() > 48 ? prompt.substring(0, 45) + "..." : prompt;

        BossBar bossBar = BossBar.bossBar(
                Component.text("Agent thinking...", NamedTextColor.AQUA),
                0.05f,
                BossBar.Color.BLUE,
                BossBar.Overlay.PROGRESS
        );
        player.showBossBar(bossBar);
        player.sendActionBar(Component.text("Agent received: " + shortPrompt, NamedTextColor.AQUA));

        // Spinner + pulsing progress so it's clearly "working" (we don't know
        // the real progress from the orchestrator, so we animate).
        final char[] frames = {'\u2599', '\u259B', '\u259C', '\u259F'}; // quadrant blocks rotation
        BukkitTask animator = plugin.getServer().getScheduler().runTaskTimer(plugin, () -> {
            long elapsed = (System.currentTimeMillis() - startMs) / 1000;
            int frame = (int) ((System.currentTimeMillis() / 200) % frames.length);
            float pulse = (float) ((System.currentTimeMillis() - startMs) % 1800L) / 1800f;
            float progress = (float) (0.15 + 0.7 * Math.sin(pulse * Math.PI));
            if (progress < 0.05f) progress = 0.05f;
            if (progress > 1.0f) progress = 1.0f;

            bossBar.name(Component.text(frames[frame] + " ", NamedTextColor.AQUA)
                    .append(Component.text("Agent · ", NamedTextColor.AQUA))
                    .append(Component.text(shortPrompt, NamedTextColor.WHITE))
                    .append(Component.text(" · " + elapsed + "s", NamedTextColor.GRAY)));
            bossBar.progress(progress);
        }, 0L, 4L); // every 4 ticks (200ms)

        OrchestratorClient.JobPayload payload = new OrchestratorClient.JobPayload(
                player.getName(),
                player.getUniqueId().toString(),
                world,
                loc.getX(),
                loc.getY(),
                loc.getZ(),
                gamemode,
                prompt
        );

        orchestrator.submitJob(payload).whenComplete((result, throwable) ->
                plugin.getServer().getScheduler().runTask(plugin, () -> {
                    animator.cancel();
                    long total = (System.currentTimeMillis() - startMs) / 1000;
                    boolean ok = throwable == null && result != null && result.ok;
                    String message = throwable != null
                            ? "Agent error: " + throwable.getMessage()
                            : (result != null ? result.message : "Unknown error");

                    bossBar.progress(1.0f);
                    if (ok) {
                        bossBar.color(BossBar.Color.GREEN);
                        bossBar.name(Component.text("Agent done · " + total + "s", NamedTextColor.GREEN));
                    } else {
                        bossBar.color(BossBar.Color.RED);
                        bossBar.name(Component.text("Agent failed · " + total + "s", NamedTextColor.RED));
                    }
                    plugin.getServer().getScheduler().runTaskLater(
                            plugin, () -> player.hideBossBar(bossBar), 50L); // 2.5s

                    NamedTextColor msgColor = ok ? NamedTextColor.GREEN : NamedTextColor.RED;
                    player.sendMessage(Component.text("[Agent] ", NamedTextColor.DARK_AQUA)
                            .append(Component.text(message, msgColor)));
                    if (ok && result != null && !result.model.isEmpty()) {
                        player.sendActionBar(Component.text(
                                result.model + " · " + result.steps + " steps · " + total + "s",
                                NamedTextColor.GRAY
                        ));
                    }
                }));

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
            List<String> hints = List.of(
                    "build",
                    "confirm",
                    "mine",
                    "dig",
                    "sphere",
                    "platform",
                    "haste",
                    "backup"
            );
            String prefix = args[0].toLowerCase();
            List<String> out = new ArrayList<>();
            for (String h : hints) {
                if (h.startsWith(prefix)) {
                    out.add(h);
                }
            }
            return out;
        }
        return List.of();
    }
}
