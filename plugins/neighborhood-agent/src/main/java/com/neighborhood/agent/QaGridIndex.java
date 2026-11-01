package com.neighborhood.agent;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.logging.Logger;

/**
 * Loads {@code qa-grid.json} (from {@code docs/QA_GRID.json}) and resolves a
 * block hit to a template cell via per-cell reserved AABBs (footprint-aware
 * shelf packing). Falls back to legacy origin+stride math when cells lack
 * bounds. Reloads automatically when the JSON mtime changes.
 */
final class QaGridIndex {
    record Cell(
            String templateId,
            String title,
            boolean gold,
            int row,
            int col,
            int standX,
            int standY,
            int standZ,
            int minX,
            int maxX,
            int minZ,
            int maxZ
    ) {
        boolean hasBounds() {
            return maxX >= minX && maxZ >= minZ
                    && !(minX == 0 && maxX == 0 && minZ == 0 && maxZ == 0 && standX != 0);
        }

        boolean contains(int x, int z) {
            return hasBounds() && x >= minX && x <= maxX && z >= minZ && z <= maxZ;
        }

        int area() {
            if (!hasBounds()) {
                return Integer.MAX_VALUE;
            }
            return (maxX - minX + 1) * (maxZ - minZ + 1);
        }
    }

    private final Path source;
    private final Logger logger;
    private volatile Snapshot snapshot;

    private record Snapshot(
            int originX,
            int originY,
            int originZ,
            int columns,
            int colStride,
            int rowStride,
            int maxRow,
            boolean useBounds,
            Map<Long, Cell> byRowCol,
            List<Cell> cells,
            long loadedMtimeMillis
    ) {
    }

    private QaGridIndex(Path source, Logger logger, Snapshot snapshot) {
        this.source = source;
        this.logger = logger;
        this.snapshot = snapshot;
    }

    static QaGridIndex load(Path path, Logger logger) {
        QaGridIndex index = new QaGridIndex(path, logger, emptySnapshot(path));
        index.reload(true);
        return index;
    }

    private static Snapshot emptySnapshot(Path path) {
        return new Snapshot(
                20000, 120, 20000, 10, 36, 36, -1,
                false, Map.of(), List.of(), -1L
        );
    }

    boolean ready() {
        maybeReload();
        return !snapshot.cells.isEmpty();
    }

    Path source() {
        return source;
    }

    Optional<Cell> resolve(int blockX, int blockY, int blockZ) {
        maybeReload();
        Snapshot snap = snapshot;
        if (snap.cells.isEmpty()) {
            return Optional.empty();
        }
        // Campus height band: pad floor through tall mega builds / overview.
        if (blockY < snap.originY - 4 || blockY > snap.originY + 160) {
            return Optional.empty();
        }
        if (snap.useBounds) {
            Cell best = null;
            for (Cell cell : snap.cells) {
                if (!cell.contains(blockX, blockZ)) {
                    continue;
                }
                if (best == null || cell.area() < best.area()) {
                    best = cell;
                }
            }
            return Optional.ofNullable(best);
        }
        // Legacy fixed-stride campus.
        int dx = blockX - snap.originX;
        int dz = blockZ - snap.originZ;
        if (dx < 0 || dz < 0 || snap.colStride <= 0 || snap.rowStride <= 0) {
            return Optional.empty();
        }
        int col = dx / snap.colStride;
        int row = dz / snap.rowStride;
        if (col < 0 || col >= snap.columns || row < 0 || row > snap.maxRow) {
            return Optional.empty();
        }
        int localX = dx - col * snap.colStride;
        int localZ = dz - row * snap.rowStride;
        if (localX >= snap.colStride || localZ >= snap.rowStride) {
            return Optional.empty();
        }
        return Optional.ofNullable(snap.byRowCol.get(key(row, col)));
    }

    private void maybeReload() {
        if (source == null || !Files.isRegularFile(source)) {
            return;
        }
        try {
            long mtime = Files.getLastModifiedTime(source).toMillis();
            if (mtime != snapshot.loadedMtimeMillis) {
                reload(false);
            }
        } catch (IOException ignored) {
            // Keep last good snapshot.
        }
    }

    private synchronized void reload(boolean initial) {
        if (source == null || !Files.isRegularFile(source)) {
            if (initial) {
                logger.warning("QA grid index missing at " + source);
            }
            snapshot = emptySnapshot(source);
            return;
        }
        try {
            FileTime ft = Files.getLastModifiedTime(source);
            long mtime = ft.toMillis();
            if (!initial && mtime == snapshot.loadedMtimeMillis) {
                return;
            }
            String raw = Files.readString(source, StandardCharsets.UTF_8);
            JsonObject root = JsonParser.parseString(raw).getAsJsonObject();
            JsonArray origin = root.getAsJsonArray("origin");
            int originX = origin.get(0).getAsInt();
            int originY = origin.get(1).getAsInt();
            int originZ = origin.get(2).getAsInt();
            int columns = root.has("columns") ? root.get("columns").getAsInt() : 10;
            int colStride = root.has("col_stride") ? root.get("col_stride").getAsInt() : 0;
            int rowStride = root.has("row_stride") ? root.get("row_stride").getAsInt() : 0;
            Map<Long, Cell> byRowCol = new HashMap<>();
            List<Cell> cells = new ArrayList<>();
            int maxRow = -1;
            int withBounds = 0;
            JsonArray cellArr = root.has("cells") ? root.getAsJsonArray("cells") : new JsonArray();
            for (JsonElement element : cellArr) {
                if (!element.isJsonObject()) {
                    continue;
                }
                JsonObject item = element.getAsJsonObject();
                String id = item.get("template_id").getAsString();
                String title = item.has("title") ? item.get("title").getAsString() : id;
                boolean gold = item.has("gold") && item.get("gold").getAsBoolean();
                int row = item.get("row").getAsInt();
                int col = item.get("col").getAsInt();
                int standX = item.get("stand_x").getAsInt();
                int standY = item.get("stand_y").getAsInt();
                int standZ = item.get("stand_z").getAsInt();
                int minX = item.has("min_x") ? item.get("min_x").getAsInt() : 0;
                int maxX = item.has("max_x") ? item.get("max_x").getAsInt() : 0;
                int minZ = item.has("min_z") ? item.get("min_z").getAsInt() : 0;
                int maxZ = item.has("max_z") ? item.get("max_z").getAsInt() : 0;
                // Derive bounds from stand + reserved size when explicit AABB missing.
                if ((maxX < minX || (minX == 0 && maxX == 0))
                        && item.has("reserved_w") && item.has("reserved_d")) {
                    int rw = item.get("reserved_w").getAsInt();
                    int rd = item.get("reserved_d").getAsInt();
                    if (rw > 0 && rd > 0) {
                        minX = standX - rw / 2;
                        maxX = minX + rw - 1;
                        minZ = standZ - 2;
                        maxZ = minZ + rd - 1;
                    }
                }
                Cell cell = new Cell(
                        id, title, gold, row, col,
                        standX, standY, standZ,
                        minX, maxX, minZ, maxZ
                );
                if (cell.hasBounds()) {
                    withBounds++;
                }
                maxRow = Math.max(maxRow, row);
                byRowCol.put(key(row, col), cell);
                cells.add(cell);
            }
            boolean useBounds = withBounds >= Math.max(1, cells.size() / 2);
            snapshot = new Snapshot(
                    originX, originY, originZ, columns, colStride, rowStride, maxRow,
                    useBounds,
                    Collections.unmodifiableMap(byRowCol),
                    List.copyOf(cells),
                    mtime
            );
            String mode = useBounds ? "AABB" : "stride";
            logger.info(
                    "Loaded QA grid index: " + cells.size() + " cells (" + mode
                            + ") from " + source.getFileName()
            );
        } catch (IOException | RuntimeException error) {
            logger.warning("Failed to load QA grid index: " + error.getMessage());
            if (initial) {
                snapshot = emptySnapshot(source);
            }
        }
    }

    private static long key(int row, int col) {
        return (((long) row) << 32) ^ (col & 0xffffffffL);
    }
}
