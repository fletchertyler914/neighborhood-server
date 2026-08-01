package com.neighborhood.agent;

import net.kyori.adventure.bossbar.BossBar;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
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

    private static final List<String> CAPABILITY_EXAMPLES = List.of(
            "make it daytime",
            "give me three dirt",
            "spawn three chickens",
            "build me a chicken coop",
            "finish this wall 8 blocks high",
            "undo that"
    );

    private final NeighborhoodAgentPlugin plugin;
    private final CompanionGateway gateway;

    public AgentCommand(NeighborhoodAgentPlugin plugin, CompanionGateway gateway) {
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
        if (!(sender instanceof Player player)) {
            sender.sendMessage(Component.text("Only players can use /agent.", NamedTextColor.RED));
            return true;
        }
        if (!player.hasPermission("neighborhood.agent")) {
            player.sendMessage(Component.text(
                    "You can't use the sidekick here. Try: ask a grown-up for help.",
                    NamedTextColor.RED
            ));
            return true;
        }
        if (args.length == 0) {
            player.sendMessage(Component.text("Hi! I'm your Minecraft sidekick.", NamedTextColor.AQUA));
            player.sendMessage(Component.text("Try one of these:", NamedTextColor.YELLOW));
            for (String example : CAPABILITY_EXAMPLES) {
                player.sendMessage(Component.text("  /agent " + example, NamedTextColor.GRAY));
            }
            return true;
        }

        String prompt = String.join(" ", args);

        long startMs = System.currentTimeMillis();
        String shortPrompt = prompt.length() > 48 ? prompt.substring(0, 45) + "..." : prompt;

        BossBar bossBar = BossBar.bossBar(
                Component.text("Sidekick working...", NamedTextColor.AQUA),
                0.05f,
                BossBar.Color.BLUE,
                BossBar.Overlay.PROGRESS
        );
        player.showBossBar(bossBar);
        player.sendActionBar(Component.text("Got it: " + shortPrompt, NamedTextColor.AQUA));

        // Spinner + pulsing progress so it's clearly "working" (we don't know
        // the real progress from the companion, so we animate).
        final char[] frames = {'\u2599', '\u259B', '\u259C', '\u259F'}; // quadrant blocks rotation
        BukkitTask animator = plugin.getServer().getScheduler().runTaskTimer(plugin, () -> {
            long elapsed = (System.currentTimeMillis() - startMs) / 1000;
            int frame = (int) ((System.currentTimeMillis() / 200) % frames.length);
            float pulse = (float) ((System.currentTimeMillis() - startMs) % 1800L) / 1800f;
            float progress = (float) (0.15 + 0.7 * Math.sin(pulse * Math.PI));
            if (progress < 0.05f) progress = 0.05f;
            if (progress > 1.0f) progress = 1.0f;

            bossBar.name(Component.text(frames[frame] + " ", NamedTextColor.AQUA)
                    .append(Component.text("Sidekick · ", NamedTextColor.AQUA))
                    .append(Component.text(shortPrompt, NamedTextColor.WHITE))
                    .append(Component.text(" · " + elapsed + "s", NamedTextColor.GRAY)));
            bossBar.progress(progress);
        }, 0L, 4L); // every 4 ticks (200ms)

        CompanionGateway.JobPayload payload = CompanionGateway.JobPayload.from(
                player,
                prompt,
                gateway.perception()
        );

        gateway.submitJob(payload).whenComplete((result, throwable) ->
                plugin.getServer().getScheduler().runTask(plugin, () -> {
                    animator.cancel();
                    long total = (System.currentTimeMillis() - startMs) / 1000;
                    boolean ok = throwable == null && result != null && result.ok();
                    String message = throwable != null
                            ? "Something went wrong. Try: make it daytime"
                            : (result != null ? result.message() : "Something went wrong. Try: make it daytime");

                    // Instant denials: hide the bar quickly so kids aren't stuck waiting.
                    long hideDelayTicks = ok ? 50L : 20L;
                    bossBar.progress(1.0f);
                    if (ok) {
                        bossBar.color(BossBar.Color.GREEN);
                        bossBar.name(Component.text("Sidekick done · " + total + "s", NamedTextColor.GREEN));
                    } else {
                        bossBar.color(BossBar.Color.RED);
                        bossBar.name(Component.text("Sidekick paused", NamedTextColor.RED));
                    }
                    plugin.getServer().getScheduler().runTaskLater(
                            plugin, () -> player.hideBossBar(bossBar), hideDelayTicks);

                    NamedTextColor msgColor = ok ? NamedTextColor.GREEN : NamedTextColor.RED;
                    player.sendMessage(Component.text("[Sidekick] ", NamedTextColor.DARK_AQUA)
                            .append(Component.text(message, msgColor)));
                    if (ok && result != null) {
                        player.sendActionBar(Component.text(
                                "All set · " + total + "s",
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
            String prefix = args[0].toLowerCase();
            List<String> out = new ArrayList<>();
            for (String h : CAPABILITY_EXAMPLES) {
                if (h.startsWith(prefix)) {
                    out.add(h);
                }
            }
            return out;
        }
        return List.of();
    }
}
