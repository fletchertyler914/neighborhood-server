package com.neighborhood.agent;

import com.google.gson.JsonObject;
import com.neighborhood.agent.NativeToolRegistry.ToolResult;
import org.bukkit.Material;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.List;
import java.util.Locale;

/**
 * Start / finish / cancel ordered path & bridge markers (Flow A).
 */
final class MarkRouteExecutor {
    private static final int GIVE_MARKERS = 8;

    private final PathMarkerSessions sessions;
    private final PlaceShapeExecutor placeShapeExecutor;
    private final String displayName;

    MarkRouteExecutor(
            PathMarkerSessions sessions,
            PlaceShapeExecutor placeShapeExecutor,
            String displayName
    ) {
        this.sessions = sessions;
        this.placeShapeExecutor = placeShapeExecutor;
        this.displayName = displayName == null || displayName.isBlank() ? "Crafter" : displayName;
    }

    PathMarkerSessions sessions() {
        return sessions;
    }

    ToolResult execute(Player player, JsonObject arguments, long started) {
        if (!player.hasPermission("neighborhood.agent.build")) {
            return ToolResult.fail("I can't build here. Try: ask a grown-up for help.", elapsed(started));
        }
        String action = requiredString(arguments, "action").toLowerCase(Locale.ROOT);
        String kindRaw = optionalString(arguments, "kind");
        PathMarkerSessions.Kind kind = parseKind(kindRaw);
        return switch (action) {
            case "start" -> start(player, kind, started);
            case "cancel" -> cancel(player, started);
            case "finish" -> finish(player, arguments, kind, started);
            case "status" -> status(player, started);
            default -> ToolResult.fail("Try: start marking a path — or finish the path.", elapsed(started));
        };
    }

    private ToolResult start(Player player, PathMarkerSessions.Kind kind, long started) {
        if (kind == null) {
            return ToolResult.fail(
                    "Path or bridge? Try: start marking a path",
                    elapsed(started)
            );
        }
        sessions.start(player.getUniqueId(), kind);
        Material marker = sessions.markerBlock();
        player.getInventory().addItem(new ItemStack(marker, GIVE_MARKERS));
        String label = kind == PathMarkerSessions.Kind.BRIDGE ? "bridge" : "path";
        String blockName = marker.getKey().getKey().replace('_', ' ');
        return ToolResult.ok(
                "Okay! I gave you " + GIVE_MARKERS + " " + blockName
                        + "s. Place them where the " + label
                        + " should go (in order). Only blocks you place after this count — "
                        + "other gold builds are ignored. I’ll say Marker N saved as you go."
                        + " When you’re done, say: finish the " + label + ".",
                true,
                elapsed(started)
        );
    }

    private ToolResult cancel(Player player, long started) {
        sessions.clear(player.getUniqueId());
        return ToolResult.ok("Okay, I stopped marking.", true, elapsed(started));
    }

    private ToolResult status(Player player, long started) {
        PathMarkerSessions.Session session = sessions.get(player.getUniqueId());
        if (session == null) {
            return ToolResult.ok(
                    "You’re not marking right now. Try: start marking a path",
                    true,
                    elapsed(started)
            );
        }
        String label = session.kind() == PathMarkerSessions.Kind.BRIDGE ? "bridge" : "path";
        int length = PathMarkerSessions.approxRouteLength(session.markers());
        String lengthBit = session.markers().size() >= 2
                ? " (~" + length + " blocks)"
                : "";
        return ToolResult.ok(
                "Marking a " + label + " — " + session.markers().size()
                        + " markers so far" + lengthBit + ". Say: finish the " + label,
                true,
                elapsed(started)
        );
    }

    private ToolResult finish(
            Player player, JsonObject arguments, PathMarkerSessions.Kind kindHint, long started
    ) {
        PathMarkerSessions.Session session = sessions.get(player.getUniqueId());
        List<PathMarkerSessions.BlockPos> markers = sessions.resolveFinishMarkers(player);
        PathMarkerSessions.Kind kind = session != null
                ? session.kind()
                : (kindHint != null ? kindHint : PathMarkerSessions.Kind.PATH);
        if (kindHint != null && (session == null || session.markers().isEmpty())) {
            kind = kindHint;
        }
        if (markers.size() < 2) {
            String label = kind == PathMarkerSessions.Kind.BRIDGE ? "bridge" : "path";
            return ToolResult.fail(
                    "I only count gold you place after “start marking a " + label
                            + "”. Place at least 2, then finish the " + label + ".",
                    elapsed(started)
            );
        }
        String mode = kind == PathMarkerSessions.Kind.BRIDGE ? "bridge" : "path";
        Material material = resolveMaterial(player, optionalString(arguments, "material"), mode);
        if (material == null) {
            return ToolResult.fail(
                    "Hold the block you want, or say the material. Try: finish the path with gravel",
                    elapsed(started)
            );
        }
        boolean clearSite = optionalBoolean(arguments, "clear_site");
        int width = clamp(optionalInt(arguments, "width", 3), 1, 8);
        ToolResult result = placeShapeExecutor.connectWaypoints(
                player, markers, material, mode, width, clearSite, started
        );
        if (result.ok()) {
            sessions.clear(player.getUniqueId());
        }
        return result;
    }

    private static PathMarkerSessions.Kind parseKind(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        return switch (raw.toLowerCase(Locale.ROOT)) {
            case "bridge" -> PathMarkerSessions.Kind.BRIDGE;
            case "path", "road", "trail" -> PathMarkerSessions.Kind.PATH;
            default -> null;
        };
    }

    private static Material resolveMaterial(Player player, String requested, String mode) {
        if (requested != null && !requested.isBlank()) {
            Material material = Material.matchMaterial(
                    requested.toLowerCase(Locale.ROOT).replace("minecraft:", "")
            );
            if (material != null && material.isBlock() && !material.isAir()) {
                return material;
            }
            return null;
        }
        var hand = player.getInventory().getItemInMainHand();
        if (hand != null && hand.getType().isBlock() && !hand.getType().isAir()) {
            return hand.getType();
        }
        return switch (mode) {
            case "bridge" -> Material.OAK_PLANKS;
            case "path" -> Material.DIRT_PATH;
            default -> Material.COBBLESTONE;
        };
    }

    private static boolean optionalBoolean(JsonObject arguments, String key) {
        if (!arguments.has(key) || arguments.get(key).isJsonNull()) {
            return false;
        }
        if (!arguments.get(key).isJsonPrimitive()) {
            return false;
        }
        var primitive = arguments.get(key).getAsJsonPrimitive();
        if (primitive.isBoolean()) {
            return primitive.getAsBoolean();
        }
        return "true".equalsIgnoreCase(primitive.getAsString());
    }

    private static int optionalInt(JsonObject arguments, String key, int defaultValue) {
        if (!arguments.has(key) || arguments.get(key).isJsonNull()) {
            return defaultValue;
        }
        return arguments.get(key).getAsInt();
    }

    private static String optionalString(JsonObject arguments, String key) {
        if (!arguments.has(key) || arguments.get(key).isJsonNull()) {
            return null;
        }
        return arguments.get(key).getAsString();
    }

    private static String requiredString(JsonObject arguments, String key) {
        String value = optionalString(arguments, key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(key);
        }
        return value;
    }

    private static int clamp(int value, int min, int max) {
        return Math.max(min, Math.min(max, value));
    }

    private static int elapsed(long started) {
        return (int) ((System.nanoTime() - started) / 1_000_000L);
    }
}
