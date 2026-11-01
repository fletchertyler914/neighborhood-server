package com.neighborhood.agent;

import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Logger;

/**
 * Per-player ordered waypoints for path/bridge marking (Flow A).
 * Sessions are persisted so restarts / missed place-events still finish the route.
 */
final class PathMarkerSessions {
    static final int MAX_MARKERS = 64;

    enum Kind {
        PATH,
        BRIDGE
    }

    record Session(Kind kind, Material markerBlock, List<BlockPos> markers, long startedMs) {
        Session withMarker(BlockPos pos) {
            List<BlockPos> next = new ArrayList<>(markers);
            next.add(pos);
            return new Session(kind, markerBlock, List.copyOf(next), startedMs);
        }

        Session withMarkers(List<BlockPos> next) {
            return new Session(kind, markerBlock, List.copyOf(next), startedMs);
        }
    }

    record BlockPos(String world, int x, int y, int z) {
        static BlockPos of(Block block) {
            return new BlockPos(
                    block.getWorld().getName(),
                    block.getX(),
                    block.getY(),
                    block.getZ()
            );
        }

        static BlockPos of(Location loc) {
            return new BlockPos(
                    loc.getWorld().getName(),
                    loc.getBlockX(),
                    loc.getBlockY(),
                    loc.getBlockZ()
            );
        }

        boolean sameColumn(BlockPos other) {
            return world.equals(other.world) && x == other.x && z == other.z;
        }

        long columnKey() {
            return (((long) x) << 32) ^ (z & 0xffffffffL);
        }
    }

    private final Map<UUID, Session> sessions = new ConcurrentHashMap<>();
    private final Material markerBlock;
    private final File storeFile;
    private final Logger logger;

    PathMarkerSessions(Material markerBlock, JavaPlugin plugin) {
        this.markerBlock = markerBlock == null ? Material.GOLD_BLOCK : markerBlock;
        this.storeFile = new File(plugin.getDataFolder(), "path-markers.yml");
        this.logger = plugin.getLogger();
        load();
    }

    Material markerBlock() {
        return markerBlock;
    }

    Session get(UUID playerId) {
        return sessions.get(playerId);
    }

    Session start(UUID playerId, Kind kind) {
        Session session = new Session(kind, markerBlock, List.of(), System.currentTimeMillis());
        sessions.put(playerId, session);
        persist();
        return session;
    }

    void clear(UUID playerId) {
        sessions.remove(playerId);
        persist();
    }

    boolean isMarking(UUID playerId) {
        return sessions.containsKey(playerId);
    }

    enum PlaceResult {
        IGNORED,
        RECORDED,
        FULL
    }

    PlaceResult recordPlacement(Player player, Block block) {
        Session session = sessions.get(player.getUniqueId());
        if (session == null) {
            return PlaceResult.IGNORED;
        }
        if (block.getType() != session.markerBlock()) {
            return PlaceResult.IGNORED;
        }
        if (!block.getWorld().equals(player.getWorld())) {
            return PlaceResult.IGNORED;
        }
        BlockPos pos = BlockPos.of(block);
        for (BlockPos existing : session.markers()) {
            if (existing.sameColumn(pos)) {
                return PlaceResult.IGNORED;
            }
        }
        if (session.markers().size() >= MAX_MARKERS) {
            return PlaceResult.FULL;
        }
        sessions.put(player.getUniqueId(), session.withMarker(pos));
        persist();
        return PlaceResult.RECORDED;
    }

    /** Drop a broken marker from the active session (same column). */
    boolean recordBreak(Player player, Block block) {
        Session session = sessions.get(player.getUniqueId());
        if (session == null) {
            return false;
        }
        BlockPos broken = BlockPos.of(block);
        List<BlockPos> kept = new ArrayList<>();
        boolean removed = false;
        for (BlockPos existing : session.markers()) {
            if (existing.sameColumn(broken)) {
                removed = true;
                continue;
            }
            kept.add(existing);
        }
        if (!removed) {
            return false;
        }
        sessions.put(player.getUniqueId(), session.withMarkers(kept));
        persist();
        return true;
    }

    /**
     * Markers to finish: <strong>only</strong> waypoints recorded while this
     * player was marking (place events). Never invents routes from decorative
     * gold builds nearby.
     */
    List<BlockPos> resolveFinishMarkers(Player player) {
        Session session = sessions.get(player.getUniqueId());
        if (session == null || session.markers().isEmpty()) {
            return List.of();
        }
        List<BlockPos> ordered = new ArrayList<>();
        Set<Long> used = new HashSet<>();
        World world = player.getWorld();
        for (BlockPos marker : session.markers()) {
            if (!marker.world().equals(world.getName())) {
                continue;
            }
            // Prefer the exact recorded block if it is still gold; else same column near that Y.
            BlockPos live = refreshRecordedMarker(world, marker);
            if (live == null) {
                // Marker was broken — keep the recorded coordinate so the route still spans.
                live = marker;
            }
            if (used.add(live.columnKey())) {
                ordered.add(live);
            }
        }
        return ordered;
    }

    static int approxRouteLength(List<BlockPos> markers) {
        if (markers == null || markers.size() < 2) {
            return 0;
        }
        int total = 0;
        for (int i = 0; i < markers.size() - 1; i++) {
            BlockPos a = markers.get(i);
            BlockPos b = markers.get(i + 1);
            if (!a.world().equals(b.world())) {
                continue;
            }
            total += BridgeSpan.lineLengthWithStairRoom(a.x(), a.z(), b.x(), b.z(), a.y(), b.y());
        }
        return total;
    }

    /**
     * Refresh a recorded marker to the live gold block at that spot (or very
     * nearby in the same column). Does not search other columns.
     */
    private BlockPos refreshRecordedMarker(World world, BlockPos recorded) {
        Block exact = world.getBlockAt(recorded.x(), recorded.y(), recorded.z());
        if (exact.getType() == markerBlock) {
            return BlockPos.of(exact);
        }
        int minY = Math.max(world.getMinHeight(), recorded.y() - 4);
        int maxY = Math.min(world.getMaxHeight() - 1, recorded.y() + 4);
        for (int y = maxY; y >= minY; y--) {
            Block block = world.getBlockAt(recorded.x(), y, recorded.z());
            if (block.getType() == markerBlock) {
                return BlockPos.of(block);
            }
        }
        return null;
    }

    private void persist() {
        FileConfiguration yaml = new YamlConfiguration();
        for (Map.Entry<UUID, Session> entry : sessions.entrySet()) {
            String path = "players." + entry.getKey();
            Session session = entry.getValue();
            yaml.set(path + ".kind", session.kind().name());
            yaml.set(path + ".started_ms", session.startedMs());
            List<String> encoded = new ArrayList<>();
            for (BlockPos pos : session.markers()) {
                encoded.add(pos.world() + "|" + pos.x() + "|" + pos.y() + "|" + pos.z());
            }
            yaml.set(path + ".markers", encoded);
        }
        try {
            File parent = storeFile.getParentFile();
            if (parent != null && !parent.exists()) {
                //noinspection ResultOfMethodCallIgnored
                parent.mkdirs();
            }
            yaml.save(storeFile);
        } catch (IOException error) {
            logger.warning("Could not save path markers: " + error.getMessage());
        }
    }

    private void load() {
        if (!storeFile.exists()) {
            return;
        }
        FileConfiguration yaml = YamlConfiguration.loadConfiguration(storeFile);
        var players = yaml.getConfigurationSection("players");
        if (players == null) {
            return;
        }
        for (String uuidRaw : players.getKeys(false)) {
            try {
                UUID uuid = UUID.fromString(uuidRaw);
                String kindRaw = yaml.getString("players." + uuidRaw + ".kind", "PATH");
                Kind kind = "BRIDGE".equalsIgnoreCase(kindRaw) ? Kind.BRIDGE : Kind.PATH;
                long started = yaml.getLong("players." + uuidRaw + ".started_ms", System.currentTimeMillis());
                List<String> encoded = yaml.getStringList("players." + uuidRaw + ".markers");
                List<BlockPos> markers = new ArrayList<>();
                for (String row : encoded) {
                    String[] parts = row.split("\\|");
                    if (parts.length != 4) {
                        continue;
                    }
                    markers.add(new BlockPos(
                            parts[0],
                            Integer.parseInt(parts[1]),
                            Integer.parseInt(parts[2]),
                            Integer.parseInt(parts[3])
                    ));
                }
                sessions.put(uuid, new Session(kind, markerBlock, List.copyOf(markers), started));
            } catch (RuntimeException ignored) {
                // skip corrupt entry
            }
        }
    }
}
