package com.neighborhood.agent;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.block.BlockBreakEvent;
import org.bukkit.event.block.BlockPlaceEvent;

/**
 * Records ordered path/bridge markers while a player is in mark mode.
 */
final class PathMarkerListener implements Listener {
    private final PathMarkerSessions sessions;
    private final String displayName;

    PathMarkerListener(PathMarkerSessions sessions, String displayName) {
        this.sessions = sessions;
        this.displayName = displayName == null || displayName.isBlank() ? "Crafter" : displayName;
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    void onPlace(BlockPlaceEvent event) {
        Player player = event.getPlayer();
        PathMarkerSessions.PlaceResult placed = sessions.recordPlacement(player, event.getBlockPlaced());
        if (placed == PathMarkerSessions.PlaceResult.IGNORED) {
            return;
        }
        if (placed == PathMarkerSessions.PlaceResult.FULL) {
            player.sendMessage(
                    Component.text(displayName + ": ", NamedTextColor.AQUA)
                            .append(Component.text(
                                    "That’s enough markers (max "
                                            + PathMarkerSessions.MAX_MARKERS
                                            + "). Say: finish the path — or cancel marking.",
                                    NamedTextColor.YELLOW
                            ))
            );
            return;
        }
        PathMarkerSessions.Session session = sessions.get(player.getUniqueId());
        if (session == null) {
            return;
        }
        int n = session.markers().size();
        String kind = session.kind() == PathMarkerSessions.Kind.BRIDGE ? "bridge" : "path";
        int length = PathMarkerSessions.approxRouteLength(session.markers());
        int chunk = BridgeSpan.MAX_LENGTH;
        NamedTextColor bodyColor = NamedTextColor.WHITE;
        String tip;
        if (n < 2) {
            tip = "Place at least one more, then say: finish the " + kind;
        } else if (length > chunk) {
            bodyColor = NamedTextColor.YELLOW;
            int stretches = (length + chunk - 1) / chunk;
            tip = "Long route — I’ll finish it in about " + stretches
                    + " stretches. Say: finish the " + kind;
        } else {
            tip = "Say: finish the " + kind + " — or keep placing more.";
        }
        String lengthBit = n >= 2 ? " (~" + length + " blocks)." : ".";
        player.sendMessage(
                Component.text(displayName + ": ", NamedTextColor.AQUA)
                        .append(Component.text(
                                "Marker " + n + " saved" + lengthBit + " " + tip,
                                bodyColor
                        ))
        );
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    void onBreak(BlockBreakEvent event) {
        Player player = event.getPlayer();
        if (!sessions.recordBreak(player, event.getBlock())) {
            return;
        }
        PathMarkerSessions.Session session = sessions.get(player.getUniqueId());
        int n = session == null ? 0 : session.markers().size();
        player.sendMessage(
                Component.text(displayName + ": ", NamedTextColor.AQUA)
                        .append(Component.text(
                                "Removed a marker (" + n + " left).",
                                NamedTextColor.WHITE
                        ))
        );
    }
}
