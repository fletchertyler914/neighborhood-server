package com.neighborhood.agent;

import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.entity.Player;
import org.bukkit.plugin.Plugin;

import java.lang.reflect.Method;
import java.util.List;

final class BuildPolicy {
    private final NeighborhoodAgentPlugin plugin;

    BuildPolicy(NeighborhoodAgentPlugin plugin) {
        this.plugin = plugin;
    }

    String denyReason(Player player, List<Location> locations, Material material) {
        return denyPlacements(
                player,
                locations.stream().map(location -> new Placement(location, material)).toList()
        );
    }

    String denyPlacements(Player player, List<Placement> placements) {
        if (!player.hasPermission("neighborhood.agent.build")) {
            return "I can't build here. Try: ask a grown-up for help.";
        }
        Plugin griefPrevention = plugin.getServer().getPluginManager().getPlugin("GriefPrevention");
        if (griefPrevention == null || !griefPrevention.isEnabled()) {
            return null;
        }
        try {
            Method allowBuild = griefPrevention.getClass().getMethod(
                    "allowBuild",
                    Player.class,
                    Location.class,
                    Material.class
            );
            for (Placement placement : placements) {
                Object reason = allowBuild.invoke(
                        griefPrevention,
                        player,
                        placement.location(),
                        placement.material()
                );
                if (reason instanceof String text && !text.isBlank()) {
                    return "That's someone's claim. Try: ask them to /trust you.";
                }
            }
            return null;
        } catch (ReflectiveOperationException error) {
            plugin.getLogger().warning(
                    "Could not verify GriefPrevention build access: " + error.getMessage()
            );
            return "I couldn't verify that you're allowed to build there.";
        }
    }

    record Placement(Location location, Material material) {
    }
}
