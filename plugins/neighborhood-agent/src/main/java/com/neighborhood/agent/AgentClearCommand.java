package com.neighborhood.agent;

import com.sk89q.worldedit.EditSession;
import com.sk89q.worldedit.WorldEdit;
import com.sk89q.worldedit.bukkit.BukkitAdapter;
import com.sk89q.worldedit.function.pattern.Pattern;
import com.sk89q.worldedit.math.BlockVector3;
import com.sk89q.worldedit.regions.CuboidRegion;
import com.sk89q.worldedit.regions.Region;
import com.sk89q.worldedit.world.block.BlockTypes;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.jetbrains.annotations.NotNull;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Console/RCON FAWE air-clear for ops cleanup (e.g. wipe stray mega pastes).
 *
 * <pre>agent-clear-box &lt;world&gt; &lt;x1&gt; &lt;y1&gt; &lt;z1&gt; &lt;x2&gt; &lt;y2&gt; &lt;z2&gt;</pre>
 */
public final class AgentClearCommand implements CommandExecutor {
    private static final AtomicLong SEQUENCE = new AtomicLong();
    private static final long MAX_VOLUME = 80_000_000L;

    private final NeighborhoodAgentPlugin plugin;

    public AgentClearCommand(NeighborhoodAgentPlugin plugin) {
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
            sender.sendMessage(Component.text(
                    "agent-clear-box is console/RCON only.",
                    NamedTextColor.RED
            ));
            return true;
        }
        if (args.length != 7) {
            sender.sendMessage(
                    "Usage: agent-clear-box <world> <x1> <y1> <z1> <x2> <y2> <z2>"
            );
            return true;
        }
        World world = Bukkit.getWorld(args[0]);
        if (world == null) {
            sender.sendMessage("[agent-clear-box] FAIL unknown world: " + args[0]);
            return true;
        }
        final int x1;
        final int y1;
        final int z1;
        final int x2;
        final int y2;
        final int z2;
        try {
            x1 = Integer.parseInt(args[1]);
            y1 = Integer.parseInt(args[2]);
            z1 = Integer.parseInt(args[3]);
            x2 = Integer.parseInt(args[4]);
            y2 = Integer.parseInt(args[5]);
            z2 = Integer.parseInt(args[6]);
        } catch (NumberFormatException error) {
            sender.sendMessage(
                    "Usage: agent-clear-box <world> <x1> <y1> <z1> <x2> <y2> <z2>"
            );
            return true;
        }
        int minX = Math.min(x1, x2);
        int minY = Math.min(y1, y2);
        int minZ = Math.min(z1, z2);
        int maxX = Math.max(x1, x2);
        int maxY = Math.max(y1, y2);
        int maxZ = Math.max(z1, z2);
        long volume = (long) (maxX - minX + 1) * (maxY - minY + 1) * (maxZ - minZ + 1);
        if (volume < 1 || volume > MAX_VOLUME) {
            sender.sendMessage("[agent-clear-box] FAIL volume " + volume + " out of range");
            return true;
        }
        long seq = SEQUENCE.incrementAndGet();
        String summary = minX + "," + minY + "," + minZ + " -> "
                + maxX + "," + maxY + "," + maxZ + " vol=" + volume;
        sender.sendMessage("[agent-clear-box] SUBMITTED seq=" + seq + " " + summary);
        plugin.getLogger().info("[agent-clear-box] submit seq=" + seq + " " + summary);

        UUID actor = new UUID(0x4e484147454e54L, 0x51415041535445L);
        com.sk89q.worldedit.world.World weWorld = BukkitAdapter.adapt(world);

        // FAWE applies on its own queue; keep Bukkit main free.
        plugin.getServer().getScheduler().runTaskAsynchronously(plugin, () -> {
            long started = System.currentTimeMillis();
            String message;
            boolean ok;
            int changed;
            try (EditSession session = WorldEdit.getInstance()
                    .newEditSessionBuilder()
                    .world(weWorld)
                    .changeSet(true, actor)
                    .maxBlocks(-1)
                    .build()) {
                Region region = new CuboidRegion(
                        weWorld,
                        BlockVector3.at(minX, minY, minZ),
                        BlockVector3.at(maxX, maxY, maxZ)
                );
                Pattern air = BlockTypes.AIR.getDefaultState();
                changed = session.setBlocks(region, air);
                session.flushQueue();
                ok = true;
                message = "changed=" + changed + " vol=" + volume + " in "
                        + (System.currentTimeMillis() - started) + "ms";
            } catch (Exception error) {
                ok = false;
                changed = 0;
                message = String.valueOf(error.getMessage());
                plugin.getLogger().warning("[agent-clear-box] fail: " + message);
            }
            boolean success = ok;
            String finalMessage = message;
            int finalChanged = changed;
            plugin.getServer().getScheduler().runTask(plugin, () -> {
                String line = "[agent-clear-box] "
                        + (success ? "OK" : "FAIL")
                        + " seq=" + seq
                        + " changed=" + finalChanged
                        + " " + finalMessage;
                plugin.getLogger().info(line);
                Bukkit.getConsoleSender().sendMessage(line);
            });
        });
        return true;
    }
}
