package com.neighborhood.agent;

import com.google.gson.JsonObject;
import com.neighborhood.agent.NativeToolRegistry.ToolResult;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.Tag;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.block.BlockFace;
import org.bukkit.block.data.Bisected;
import org.bukkit.block.data.BlockData;
import org.bukkit.block.data.type.Door;
import org.bukkit.block.data.type.Stairs;
import org.bukkit.entity.Player;
import org.bukkit.util.Vector;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.function.BiConsumer;

/**
 * Player-relative parametric shapes for the NL world editor.
 */
final class PlaceShapeExecutor {
    private static final int MAX_WALL_CELLS = 1_536;
    private static final int MAX_PLATFORM_CELLS = 1_024;
    private static final int MAX_OUTLINE_CELLS = 4_000;
    private static final int MAX_SOLID_CELLS = 4_096;
    /** Deck footprint budget: MAX_LENGTH × max path width (8). */
    private static final int MAX_SPAN_CELLS = 8_192;
    private static final int SPAN_SCAN = BridgeSpan.MAX_LENGTH;
    private static final int PATH_HEADROOM = 3;
    static final String FAR_SHORE_MESSAGE =
            "I can't see the far shore from here. Look across the water, or try: bridge 40 long";
    /** Admin / world-integrity only — gameplay blocks including TNT are allowed. */
    private static final Set<Material> RESTRICTED = Set.of(
            Material.COMMAND_BLOCK,
            Material.CHAIN_COMMAND_BLOCK,
            Material.REPEATING_COMMAND_BLOCK,
            Material.STRUCTURE_BLOCK,
            Material.JIGSAW,
            Material.DEBUG_STICK
    );

    private final BuildPolicy buildPolicy;
    private final BiConsumer<Player, Runnable> rememberUndo;
    private final NativeToolRegistry.WallFinisher wallFinisher;
    private PathMarkerSessions markerSessions;

    PlaceShapeExecutor(
            BuildPolicy buildPolicy,
            PerceptionEngine perception,
            BiConsumer<Player, Runnable> rememberUndo,
            NativeToolRegistry.WallFinisher wallFinisher
    ) {
        this.buildPolicy = buildPolicy;
        this.rememberUndo = rememberUndo;
        this.wallFinisher = wallFinisher;
    }

    void setMarkerSessions(PathMarkerSessions markerSessions) {
        this.markerSessions = markerSessions;
    }

    ToolResult execute(Player player, JsonObject arguments, long started) {
        if (!player.hasPermission("neighborhood.agent.build")) {
            return ToolResult.fail("I can't build here. Try: ask a grown-up for help.", elapsed(started));
        }
        boolean clearSite = optionalBoolean(arguments, "clear_site");
        String kind = requiredString(arguments, "kind").toLowerCase(Locale.ROOT);
        Material material = resolveMaterial(player, optionalString(arguments, "material"));
        if (material == null && ("bridge".equals(kind) || "road".equals(kind) || "path".equals(kind))) {
            material = switch (kind) {
                case "bridge" -> Material.OAK_PLANKS;
                case "path" -> Material.DIRT_PATH;
                default -> Material.COBBLESTONE;
            };
        }
        if (material == null && "stairs_to".equals(kind)) {
            material = Material.OAK_STAIRS;
        }
        if (material == null) {
            return ToolResult.fail(
                    "Hold the block you want, or say the material. Try: 5x5 oak platform",
                    elapsed(started)
            );
        }
        if (RESTRICTED.contains(material) || !material.isBlock() || material.isAir()) {
            return ToolResult.fail(
                    RESTRICTED.contains(material)
                            ? "I can’t use admin blocks for that."
                            : "I need a real block material for that.",
                    elapsed(started)
            );
        }

        // Sized wall asks prefer finish_wall (geometry + legacy post-pair) whenever
        // an opening is visible. Only free-stand place when no opening/posts exist.
        if ("wall".equals(kind)) {
            JsonObject finishArgs = new JsonObject();
            if (arguments.has("height")) {
                finishArgs.addProperty("height", arguments.get("height").getAsInt());
            }
            if (arguments.has("material")) {
                finishArgs.addProperty("material", arguments.get("material").getAsString());
            }
            ToolResult finished = wallFinisher.finish(player, finishArgs, started);
            if (finished.ok()) {
                return finished;
            }
            String msg = finished.message() == null
                    ? ""
                    : finished.message().toLowerCase(Locale.ROOT);
            // Fall through only when perception found nothing to finish.
            if (!msg.contains("couldn't find")
                    && !msg.contains("couldn’t find")
                    && !msg.contains("look at a corner")) {
                return finished;
            }
        }

        return switch (kind) {
            case "wall" -> placeWall(player, arguments, material, started, clearSite);
            case "platform" -> placePlatform(player, arguments, material, started, clearSite);
            case "box_shell" -> placeBox(player, arguments, material, started, false, clearSite);
            case "solid_box" -> placeBox(player, arguments, material, started, true, clearSite);
            case "cylinder" -> placeCylinder(player, arguments, material, started, clearSite);
            case "bridge" -> placeSpan(player, arguments, material, started, clearSite, "bridge");
            case "road" -> placeSpan(player, arguments, material, started, clearSite, "road");
            case "path" -> placeSpan(player, arguments, material, started, clearSite, "path");
            case "stairs_to" -> placeStairsTo(player, arguments, material, started, clearSite);
            default -> ToolResult.fail("I don't know that shape.", elapsed(started));
        };
    }

    /**
     * Build ±1 stairs/steps from the ground up to a door threshold.
     * Never extends past the landing (extra run is pulled backward from the start).
     */
    private ToolResult placeStairsTo(
            Player player,
            JsonObject args,
            Material material,
            long started,
            boolean clearSite
    ) {
        World world = player.getWorld();
        Block door = findDoor(player);
        if (door == null) {
            return ToolResult.fail(
                    "Look at the door, or stand in front of it, then try again.",
                    elapsed(started)
            );
        }
        // Side facing the player = outside. Never aim into the building.
        BlockFace outward = doorOutwardTowardPlayer(door, player);
        Block landing = door.getRelative(outward);
        int endX = landing.getX();
        int endZ = landing.getZ();
        // Walk surface = floor under the door (door bottom sits in the air cell above).
        int endY = door.getY() - 1;
        if (endY < world.getMinHeight()) {
            endY = world.getMinHeight();
        }

        int startX = player.getLocation().getBlockX();
        int startZ = player.getLocation().getBlockZ();
        int feetY = player.getLocation().getBlockY();
        // Standing walk surface (pier planks / path top) — never lakebed under water.
        int standingY = walkSurfaceY(world, startX, feetY, startZ);
        int startY = standingY;
        // Keep start on the outside — never on the door or inside.
        if (startX == door.getX() && startZ == door.getZ()
                || startX == endX && startZ == endZ) {
            BlockFace away = outward.getOppositeFace();
            startX = door.getX() + away.getModX() * 3;
            startZ = door.getZ() + away.getModZ() * 3;
            startY = Math.max(standingY, walkSurfaceY(world, startX, feetY, startZ));
        }

        int horiz = BridgeSpan.lineLengthXZ(startX, startZ, endX, endZ);
        if (horiz < 2) {
            return ToolResult.fail(
                    "Stand a few blocks outside the door, then try again.",
                    elapsed(started)
            );
        }

        // Extra rise needs more run — extend BACKWARD from the player, never past the door.
        // Keep the standing deck height when the extension lands in open water.
        int need = BridgeSpan.minStairsLength(startY, endY);
        if (horiz < need) {
            int extra = need - horiz;
            int dx = Integer.signum(endX - startX);
            int dz = Integer.signum(endZ - startZ);
            if (dx == 0 && dz == 0) {
                dx = outward.getOppositeFace().getModX();
                dz = outward.getOppositeFace().getModZ();
                if (dx == 0 && dz == 0) {
                    dx = 1;
                }
            }
            startX -= dx * extra;
            startZ -= dz * extra;
            startY = Math.max(standingY, walkSurfaceY(world, startX, feetY, startZ));
            // Re-check rise after moving start (terrain may change).
            need = BridgeSpan.minStairsLength(startY, endY);
            horiz = BridgeSpan.lineLengthXZ(startX, startZ, endX, endZ);
            if (horiz < need) {
                return ToolResult.fail(
                        "I need more room outside for those stairs. Clear a path back from the door.",
                        elapsed(started)
                );
            }
        }

        // Cap climb: door threshold only — never aim above first-floor door.
        if (endY > startY + BridgeSpan.MAX_LENGTH) {
            return ToolResult.fail(
                    "That door is too high for one staircase. Try a closer entrance.",
                    elapsed(started)
            );
        }

        int[][] line = BridgeSpan.lineXZ(startX, startZ, endX, endZ);
        // Drop the final cell if it somehow entered the door column.
        if (line.length >= 2
                && line[line.length - 1][0] == door.getX()
                && line[line.length - 1][1] == door.getZ()) {
            int[][] trimmed = new int[line.length - 1][2];
            System.arraycopy(line, 0, trimmed, 0, trimmed.length);
            line = trimmed;
        }
        if (line.length < 2) {
            return ToolResult.fail(
                    "Stand a few blocks outside the door, then try again.",
                    elapsed(started)
            );
        }
        if (line.length > BridgeSpan.MAX_LENGTH) {
            return ToolResult.fail(
                    "That’s too far for stairs in one go. Move closer to the door.",
                    elapsed(started)
            );
        }
        int width = clamp(optionalInt(args, "width", 2), 1, 8);
        if (line.length * width > MAX_SPAN_CELLS) {
            return ToolResult.fail(
                    "Those stairs are too big. Try standing closer to the door.",
                    elapsed(started)
            );
        }

        // Hug outdoor grade; only climb/descend near the door. Do NOT flatten
        // the whole run to endY — that trenches under the ground whenever
        // startY is even one block above the threshold.
        int[] terrainY = new int[line.length];
        // Seed from the walk surface, not feet air — low seeds make sampleColumn
        // start already inside dirt and report an underground "surface".
        int sampleSeed = Math.max(startY, feetY);
        for (int i = 0; i < line.length; i++) {
            BridgeSpan.Column col = sampleColumn(world, line[i][0], line[i][1], sampleSeed);
            int surface;
            if (col.kind() == BridgeSpan.Kind.WATER) {
                // Deck at standing height — never lakebed (solidTopY under water).
                surface = BridgeSpan.preferWalkSurface(
                        startY, col.solidTopY(), col.surfaceY(), 4
                );
                surface = Math.max(startY, surface);
            } else if (col.isCrossing()) {
                surface = Math.max(startY, col.surfaceY());
            } else {
                surface = BridgeSpan.preferWalkSurface(
                        sampleSeed, col.surfaceY(), null, 8
                );
            }
            terrainY[i] = surface;
            // Never let the scan band fall under the walk surface we already know.
            sampleSeed = Math.max(surface, startY);
        }
        terrainY[0] = Math.max(terrainY[0], startY);
        int[] profile = BridgeSpan.stairProfileGroundHug(terrainY, startY, endY);
        if (profile.length >= 2
                && Math.abs(endY - profile[profile.length - 2]) <= BridgeSpan.MAX_STEP) {
            profile[profile.length - 1] = endY;
        } else if (profile.length == 1) {
            profile[0] = endY;
        }
        int rampStart = BridgeSpan.groundHugRampStart(terrainY, startY, endY);
        Vector forward;
        int fdx = Integer.signum(endX - startX);
        int fdz = Integer.signum(endZ - startZ);
        if (Math.abs(endX - startX) >= Math.abs(endZ - startZ)) {
            forward = new Vector(fdx == 0 ? 1 : fdx, 0, 0);
        } else {
            forward = new Vector(0, 0, fdz == 0 ? 1 : fdz);
        }
        Vector right = new Vector(forward.getZ(), 0, -forward.getX());
        int half = width / 2;

        List<Block> surface = new ArrayList<>(line.length * width);
        List<Block> clearBlocks = new ArrayList<>();
        boolean needsBuildClear = false;
        for (int i = 0; i < line.length; i++) {
            int cx = line[i][0];
            int cz = line[i][1];
            // Never pave the door column or inside the building.
            if (cx == door.getX() && cz == door.getZ()) {
                continue;
            }
            Block inward = door.getRelative(outward.getOppositeFace());
            if (cx == inward.getX() && cz == inward.getZ()) {
                continue;
            }
            int y = profile[i];
            int centerGrade = terrainY[i];
            // Approach must stay on/above grade and the standing deck (pier).
            if (i < rampStart) {
                if (y < centerGrade) {
                    y = centerGrade;
                }
                if (y < startY) {
                    y = startY;
                }
            }
            for (int w = 0; w < width; w++) {
                int lateral = w - half;
                int bx = cx + right.getBlockX() * lateral;
                int bz = cz + right.getBlockZ() * lateral;
                if (bx == door.getX() && bz == door.getZ()) {
                    continue;
                }
                int placeY = y;
                int localWalk = walkSurfaceY(world, bx, Math.max(y, startY), bz);
                // Hug nearby walk surface (±1) but never snap up a cliff face —
                // that made discontinuous jumps; never dig under the deck either.
                if (localWalk >= placeY - 1 && localWalk <= placeY + 1) {
                    placeY = Math.max(placeY, localWalk);
                }
                if (i < rampStart && placeY < startY) {
                    placeY = startY;
                }
                Block surfaceBlock = world.getBlockAt(bx, placeY, bz);
                surface.add(surfaceBlock);
                for (int dy = 1; dy <= PATH_HEADROOM; dy++) {
                    Block above = world.getBlockAt(bx, placeY + dy, bz);
                    Material mat = above.getType();
                    if (mat.isAir() || isDoorMaterial(mat)) {
                        continue;
                    }
                    if (isSoftClearable(mat)) {
                        clearBlocks.add(above);
                        continue;
                    }
                    if (!mat.isSolid() || isWater(mat)) {
                        continue;
                    }
                    // Never carve natural ground — headroom clears on dirt/grass
                    // are what dug the trench and hillside niche.
                    if (NativeSchematicPaster.isNaturalTerrain(mat)) {
                        continue;
                    }
                    needsBuildClear = true;
                    if (clearSite) {
                        clearBlocks.add(above);
                    }
                }
            }
        }
        if (surface.isEmpty()) {
            return ToolResult.fail(
                    "Stand a few blocks outside the door, then try again.",
                    elapsed(started)
            );
        }
        if (wouldOverwriteBuilds(surface, true)) {
            needsBuildClear = true;
        }
        Set<String> surfaceKeys = new HashSet<>();
        for (Block block : surface) {
            surfaceKeys.add(block.getX() + "," + block.getY() + "," + block.getZ());
        }
        Set<String> seen = new HashSet<>();
        List<Block> allClear = new ArrayList<>();
        for (Block block : clearBlocks) {
            String key = block.getX() + "," + block.getY() + "," + block.getZ();
            if (surfaceKeys.contains(key) || !seen.add(key)) {
                continue;
            }
            allClear.add(block);
        }
        if (!clearSite && needsBuildClear) {
            return ToolResult.fail(SchematicPlacement.CLEAR_ASK_MESSAGE, elapsed(started));
        }

        int px = player.getLocation().getBlockX();
        int pz = player.getLocation().getBlockZ();
        int py = player.getLocation().getBlockY();
        for (Block block : surface) {
            if (block.getX() == px && block.getZ() == pz
                    && block.getY() >= py && block.getY() <= py + 1) {
                return ToolResult.fail(
                        "You're standing on the stairs path — take one step to the side.",
                        elapsed(started)
                );
            }
        }
        List<Location> locations = new ArrayList<>(surface.size() + allClear.size());
        for (Block block : surface) {
            locations.add(block.getLocation());
        }
        for (Block block : allClear) {
            locations.add(block.getLocation());
        }
        String denied = buildPolicy.denyReason(player, locations, material);
        if (denied != null) {
            return ToolResult.fail(denied, elapsed(started));
        }

        BlockFace climbFace = toBlockFace(forward);
        BlockData placeData = stairBlockData(material, climbFace);
        Runnable undo = BoundedFaweEdit.applyMixed(
                world, player.getUniqueId(), surface, placeData, allClear
        );
        boolean verified = surface.stream().allMatch(block -> block.getType() == material);
        if (!verified) {
            undo.run();
            return ToolResult.fail(
                    "I couldn't place that exactly, so I put things back.",
                    elapsed(started)
            );
        }
        rememberUndo.accept(player, undo);
        return ToolResult.ok(
                "Built " + readable(material) + " up to the door. Say “undo that” if you don’t like it.",
                true,
                elapsed(started)
        );
    }

    private static Block findDoor(Player player) {
        GazeHit gaze = GazeSensor.capture(player);
        if (gaze.hit() && gaze.block() != null) {
            Block door = doorBottom(gaze.block());
            if (door != null) {
                return door;
            }
        }
        World world = player.getWorld();
        Vector forward = horizontalForward(player);
        Vector right = new Vector(forward.getZ(), 0, -forward.getX());
        int bx = player.getLocation().getBlockX();
        int by = player.getLocation().getBlockY();
        int bz = player.getLocation().getBlockZ();
        Block best = null;
        double bestScore = Double.MAX_VALUE;
        for (int f = 1; f <= 16; f++) {
            for (int lat = -4; lat <= 4; lat++) {
                // Prefer doors near the player's own floor — not upstairs.
                for (int dy = -4; dy <= 4; dy++) {
                    int x = bx + forward.getBlockX() * f + right.getBlockX() * lat;
                    int y = by + dy;
                    int z = bz + forward.getBlockZ() * f + right.getBlockZ() * lat;
                    if (y < world.getMinHeight() || y >= world.getMaxHeight()) {
                        continue;
                    }
                    Block door = doorBottom(world.getBlockAt(x, y, z));
                    if (door == null) {
                        continue;
                    }
                    double dist = player.getLocation().distanceSquared(
                            door.getLocation().clone().add(0.5, 0.5, 0.5)
                    );
                    double yPenalty = Math.abs(door.getY() - by) * 8.0;
                    double score = dist + yPenalty;
                    if (score < bestScore) {
                        bestScore = score;
                        best = door;
                    }
                }
            }
        }
        return best;
    }

    private static Block doorBottom(Block block) {
        if (block == null || !isDoorMaterial(block.getType())) {
            return null;
        }
        if (block.getBlockData() instanceof Bisected bisected
                && bisected.getHalf() == Bisected.Half.TOP) {
            Block below = block.getRelative(BlockFace.DOWN);
            if (isDoorMaterial(below.getType())) {
                return below;
            }
        }
        return block;
    }

    private static boolean isDoorMaterial(Material material) {
        if (material == null || material.isAir()) {
            return false;
        }
        if (Tag.DOORS.isTagged(material)) {
            return true;
        }
        String name = material.name();
        return name.endsWith("_DOOR") && !name.contains("TRAP");
    }

    /** Outside face = horizontal direction from the door toward the player. */
    private static BlockFace doorOutwardTowardPlayer(Block door, Player player) {
        int pdx = player.getLocation().getBlockX() - door.getX();
        int pdz = player.getLocation().getBlockZ() - door.getZ();
        if (pdx == 0 && pdz == 0) {
            if (door.getBlockData() instanceof Door hinged) {
                return hinged.getFacing();
            }
            return BlockFace.NORTH;
        }
        if (Math.abs(pdx) >= Math.abs(pdz)) {
            return pdx > 0 ? BlockFace.EAST : BlockFace.WEST;
        }
        return pdz > 0 ? BlockFace.SOUTH : BlockFace.NORTH;
    }

    private static BlockFace toBlockFace(Vector forward) {
        if (Math.abs(forward.getX()) >= Math.abs(forward.getZ())) {
            return forward.getX() >= 0 ? BlockFace.EAST : BlockFace.WEST;
        }
        return forward.getZ() >= 0 ? BlockFace.SOUTH : BlockFace.NORTH;
    }

    private static BlockData stairBlockData(Material material, BlockFace climbFace) {
        BlockData data = material.createBlockData();
        if (data instanceof Stairs stairs) {
            stairs.setFacing(climbFace);
            stairs.setHalf(Bisected.Half.BOTTOM);
            stairs.setShape(Stairs.Shape.STRAIGHT);
            return stairs;
        }
        return data;
    }

    private ToolResult placeSpan(
            Player player,
            JsonObject args,
            Material material,
            long started,
            boolean clearSite,
            String mode
    ) {
        boolean bridge = "bridge".equals(mode);
        boolean trail = "path".equals(mode) || "road".equals(mode);
        int width = clamp(optionalInt(args, "width", 3), 1, 8);

        // Prefer ordered markers (Flow A session), then nearby scan (Flow B).
        List<PathMarkerSessions.BlockPos> markers = resolveMarkers(player, mode);
        if (markers != null && markers.size() >= 2) {
            ToolResult marked = connectWaypoints(
                    player, markers, material, mode, width, clearSite, started
            );
            if (marked.ok() && markerSessions != null) {
                PathMarkerSessions.Session session = markerSessions.get(player.getUniqueId());
                if (session != null && !session.markers().isEmpty()) {
                    markerSessions.clear(player.getUniqueId());
                }
            }
            return marked;
        }

        Integer explicitLength = args.has("length") && !args.get("length").isJsonNull()
                ? clamp(args.get("length").getAsInt(), 2, BridgeSpan.MAX_LENGTH)
                : null;
        Vector forward = horizontalForward(player);
        Vector right = new Vector(forward.getZ(), 0, -forward.getX());
        Location feet = player.getLocation().getBlock().getLocation();
        int px = feet.getBlockX();
        int py = feet.getBlockY();
        int pz = feet.getBlockZ();
        World world = player.getWorld();

        BridgeSpan.Column[] columns = new BridgeSpan.Column[SPAN_SCAN];
        for (int i = 0; i < SPAN_SCAN; i++) {
            int dist = i + 1;
            int cx = px + forward.getBlockX() * dist;
            int cz = pz + forward.getBlockZ() * dist;
            columns[i] = sampleColumn(world, cx, cz, py);
        }
        int fallbackDeckY = walkSurfaceY(world, px, py, pz);
        BridgeSpan.Result span = bridge
                ? BridgeSpan.resolveBridge(columns, explicitLength, fallbackDeckY)
                : BridgeSpan.resolvePath(columns, explicitLength, fallbackDeckY);
        if (span == null) {
            return ToolResult.fail(FAR_SHORE_MESSAGE, elapsed(started));
        }
        if (span.length() * width > MAX_SPAN_CELLS) {
            return ToolResult.fail(
                    "That " + mode + " is too big. Try a shorter span (up to "
                            + BridgeSpan.MAX_LENGTH + ").",
                    elapsed(started)
            );
        }

        int half = width / 2;
        int[] profile;
        if (span.crossedGap() && bridge) {
            profile = new int[span.length()];
            for (int i = 0; i < profile.length; i++) {
                int dist = span.startDist() + i;
                BridgeSpan.Column col = columns[dist - 1];
                if (col.kind() == BridgeSpan.Kind.LAND) {
                    profile[i] = Math.max(col.surfaceY(), span.deckY());
                } else {
                    profile[i] = span.deckY();
                }
            }
        } else {
            profile = BridgeSpan.walkableProfile(
                    columns, span.startDist(), span.endDist(), fallbackDeckY
            );
            // Surface-follow: never leave land cells under grade.
            for (int i = 0; i < profile.length; i++) {
                int dist = span.startDist() + i;
                BridgeSpan.Column col = columns[dist - 1];
                if (!col.isCrossing() && profile[i] < col.surfaceY()) {
                    profile[i] = col.surfaceY();
                }
            }
            for (int i = 1; i < profile.length; i++) {
                int prev = profile[i - 1];
                if (profile[i] > prev + BridgeSpan.MAX_STEP) {
                    profile[i] = prev + BridgeSpan.MAX_STEP;
                } else if (profile[i] < prev - BridgeSpan.MAX_STEP) {
                    profile[i] = prev - BridgeSpan.MAX_STEP;
                }
                int dist = span.startDist() + i;
                BridgeSpan.Column col = columns[dist - 1];
                if (!col.isCrossing() && profile[i] < col.surfaceY()) {
                    profile[i] = Math.min(col.surfaceY(), prev + BridgeSpan.MAX_STEP);
                }
            }
        }

        List<Block> surface = new ArrayList<>();
        List<Block> clearBlocks = new ArrayList<>();
        boolean needsBuildClear = false;
        for (int i = 0; i < profile.length; i++) {
            int dist = span.startDist() + i;
            int cx = px + forward.getBlockX() * dist;
            int cz = pz + forward.getBlockZ() * dist;
            int y = profile[i];
            for (int w = 0; w < width; w++) {
                int lateral = w - half;
                int bx = cx + right.getBlockX() * lateral;
                int bz = cz + right.getBlockZ() * lateral;
                surface.add(world.getBlockAt(bx, y, bz));
                if (trail) {
                    // Clear soft headroom only — never excavate natural ground
                    // into a trench (path-marker / hillside failure mode).
                    for (int dy = 1; dy <= PATH_HEADROOM; dy++) {
                        Block above = world.getBlockAt(bx, y + dy, bz);
                        Material mat = above.getType();
                        if (mat.isAir()) {
                            continue;
                        }
                        if (isSoftClearable(mat)) {
                            clearBlocks.add(above);
                        } else if (mat.isSolid() && !isWater(mat)
                                && !NativeSchematicPaster.isNaturalTerrain(mat)) {
                            needsBuildClear = true;
                            if (clearSite) {
                                clearBlocks.add(above);
                            }
                        }
                    }
                }
            }
        }

        if (!clearSite && (needsBuildClear || wouldOverwriteBuilds(surface, true))) {
            return ToolResult.fail(SchematicPlacement.CLEAR_ASK_MESSAGE, elapsed(started));
        }

        String label = mode;
        return applyCorridor(
                player,
                surface,
                clearBlocks,
                material,
                started,
                "Built a " + readable(material) + " " + label + " ("
                        + span.length() + " long, " + width + " wide).",
                true
        );
    }

    private List<PathMarkerSessions.BlockPos> resolveMarkers(Player player, String mode) {
        if (markerSessions == null) {
            return null;
        }
        List<PathMarkerSessions.BlockPos> markers = markerSessions.resolveFinishMarkers(player);
        return markers.size() >= 2 ? markers : null;
    }

    /**
     * Connect ordered waypoints with a walkable path (land) and water-level
     * bridge decks (water). Streams marker→marker polylines in
     * {@link BridgeSpan#MAX_LENGTH} coordinate chunks — no overall length cap.
     */
    ToolResult connectWaypoints(
            Player player,
            List<PathMarkerSessions.BlockPos> markers,
            Material material,
            String mode,
            int width,
            boolean clearSite,
            long started
    ) {
        if (markers == null || markers.size() < 2) {
            return ToolResult.fail(
                    "I need at least 2 markers. Try: start marking a path",
                    elapsed(started)
            );
        }
        World world = player.getWorld();
        for (PathMarkerSessions.BlockPos marker : markers) {
            if (!marker.world().equals(world.getName())) {
                return ToolResult.fail(
                        "Those markers are in another world. Stay in one place and try again.",
                        elapsed(started)
                );
            }
        }
        width = clamp(width, 1, 8);
        boolean trail = !"bridge".equals(mode);

        // Dry-run: ask before clear without applying anything.
        if (!clearSite) {
            ClearProbe probe = streamRoute(
                    player, markers, material, mode, width, trail, false, false, null
            );
            if (probe.denied != null) {
                return ToolResult.fail(probe.denied, elapsed(started));
            }
            if (probe.needsBuildClear) {
                return ToolResult.fail(SchematicPlacement.CLEAR_ASK_MESSAGE, elapsed(started));
            }
        }

        List<Runnable> undos = new ArrayList<>();
        ClearProbe applied = streamRoute(
                player, markers, material, mode, width, trail, true, clearSite, undos
        );
        if (applied.denied != null) {
            rollbackAll(undos);
            return ToolResult.fail(applied.denied, elapsed(started));
        }
        if (applied.totalSteps < 2 || applied.chunksApplied == 0) {
            rollbackAll(undos);
            return ToolResult.fail("I couldn't find a clear spot for that.", elapsed(started));
        }

        // Clear leftover gold markers that weren't overwritten as surface.
        List<Block> leftoverMarkers = new ArrayList<>();
        if (markerSessions != null) {
            Material markerMat = markerSessions.markerBlock();
            for (PathMarkerSessions.BlockPos marker : markers) {
                Block block = world.getBlockAt(marker.x(), marker.y(), marker.z());
                if (block.getType() == markerMat) {
                    leftoverMarkers.add(block);
                }
            }
        }
        if (!leftoverMarkers.isEmpty()) {
            try {
                undos.add(BoundedFaweEdit.applyMixed(
                        world, player.getUniqueId(), List.of(), material, leftoverMarkers
                ));
            } catch (RuntimeException error) {
                rollbackAll(undos);
                return ToolResult.fail(
                        "I couldn't place that exactly, so I put things back.",
                        elapsed(started)
                );
            }
        }

        rememberUndo.accept(player, () -> rollbackAll(undos));
        String label = "bridge".equals(mode) ? "bridge" : "path";
        String okMessage = "Connected all " + markers.size() + " markers with "
                + readable(material)
                + ("bridge".equals(label) ? " bridge" : "")
                + (applied.chunksApplied > 1 ? " (" + applied.chunksApplied + " stretches)" : "")
                + ".";
        return ToolResult.ok(
                okMessage + " Say “undo that” if you don’t like it.",
                true,
                elapsed(started)
        );
    }

    private static final class ClearProbe {
        boolean needsBuildClear;
        String denied;
        int totalSteps;
        int chunksApplied;
    }

    private static final class CorridorChunk {
        final List<Block> surface;
        final List<Block> clear;
        final boolean needsBuildClear;
        final int seedY;

        CorridorChunk(List<Block> surface, List<Block> clear, boolean needsBuildClear, int seedY) {
            this.surface = surface;
            this.clear = clear;
            this.needsBuildClear = needsBuildClear;
            this.seedY = seedY;
        }
    }

    private static Vector spanRight(PathMarkerSessions.BlockPos a, PathMarkerSessions.BlockPos b) {
        int fdx = Integer.signum(b.x() - a.x());
        int fdz = Integer.signum(b.z() - a.z());
        if (fdx == 0 && fdz == 0) {
            fdx = 1;
        }
        Vector forward;
        if (Math.abs(b.x() - a.x()) >= Math.abs(b.z() - a.z())) {
            forward = new Vector(fdx == 0 ? 1 : fdx, 0, 0);
        } else {
            forward = new Vector(0, 0, fdz == 0 ? 1 : fdz);
        }
        return new Vector(forward.getZ(), 0, -forward.getX());
    }

    /**
     * Walk every marker leg in {@link BridgeSpan#MAX_LENGTH} coordinate boxes.
     * Marker Y anchors drive ±1 stair ramps; legs extend when rise needs more run.
     */
    private ClearProbe streamRoute(
            Player player,
            List<PathMarkerSessions.BlockPos> markers,
            Material material,
            String mode,
            int width,
            boolean trail,
            boolean apply,
            boolean clearSite,
            List<Runnable> undos
    ) {
        ClearProbe probe = new ClearProbe();
        World world = player.getWorld();
        int px = player.getLocation().getBlockX();
        int pz = player.getLocation().getBlockZ();
        int py = player.getLocation().getBlockY();
        boolean bridge = "bridge".equals(mode);

        for (int m = 0; m < markers.size() - 1; m++) {
            PathMarkerSessions.BlockPos a = markers.get(m);
            PathMarkerSessions.BlockPos b = markers.get(m + 1);
            int startY = walkSurfaceY(world, a.x(), a.y() + 1, a.z());
            int endY = walkSurfaceY(world, b.x(), b.y() + 1, b.z());
            // Markers are solid gold — keep at least the recorded block Y so we
            // replace them, but never a deep solid under the marker band.
            startY = Math.max(startY, preferMarkerWalkY(world, a));
            endY = Math.max(endY, preferMarkerWalkY(world, b));
            int deckFloor = Math.min(startY, endY);
            int[] end = BridgeSpan.extendedEnd(a.x(), a.z(), b.x(), b.z(), startY, endY);
            int x1 = end[0];
            int z1 = end[1];
            PathMarkerSessions.BlockPos endPos = new PathMarkerSessions.BlockPos(
                    b.world(), x1, endY, z1
            );
            Vector right = spanRight(a, endPos);
            int half = width / 2;
            int legLen = BridgeSpan.lineLengthXZ(a.x(), a.z(), x1, z1);
            if (legLen < 1) {
                continue;
            }
            int[] profile = BridgeSpan.stairProfile(legLen, startY, endY);
            BridgeSpan.LineCursor cursor = BridgeSpan.LineCursor.start(a.x(), a.z(), x1, z1);
            int index = 0;
            int sampleSeed = startY;
            while (cursor.hasNext()) {
                int[][] line = cursor.nextChunk(BridgeSpan.MAX_LENGTH);
                if (line.length == 0) {
                    break;
                }
                BridgeSpan.Column[] columns = new BridgeSpan.Column[line.length];
                int[] chunkProfile = new int[line.length];
                for (int i = 0; i < line.length; i++) {
                    columns[i] = sampleColumn(world, line[i][0], line[i][1], sampleSeed);
                    int rawSurface = columns[i].surfaceY();
                    if (columns[i].kind() == BridgeSpan.Kind.WATER) {
                        rawSurface = BridgeSpan.preferWalkSurface(
                                sampleSeed, columns[i].solidTopY(), columns[i].surfaceY(), 4
                        );
                    }
                    sampleSeed = Math.max(rawSurface, startY);
                    int ramp = profile[index + i];
                    int y = BridgeSpan.trailFollowY(
                            ramp,
                            rawSurface,
                            columns[i].isCrossing(),
                            deckFloor
                    );
                    if (trail && !bridge && !columns[i].isCrossing()) {
                        // Surface-follow hills — never keep a ramp under grade.
                        y = Math.max(y, columns[i].surfaceY());
                    } else if (columns[i].isCrossing()) {
                        y = Math.max(y, Math.max(rawSurface, startY));
                    }
                    if (i > 0) {
                        int prev = chunkProfile[i - 1];
                        if (y > prev + BridgeSpan.MAX_STEP) {
                            y = prev + BridgeSpan.MAX_STEP;
                        } else if (y < prev - BridgeSpan.MAX_STEP) {
                            y = prev - BridgeSpan.MAX_STEP;
                        }
                    } else if (index > 0) {
                        int prev = profile[index - 1];
                        // Keep continuity with prior chunk's intended ramp.
                        if (y > prev + BridgeSpan.MAX_STEP) {
                            y = prev + BridgeSpan.MAX_STEP;
                        } else if (y < prev - BridgeSpan.MAX_STEP) {
                            y = prev - BridgeSpan.MAX_STEP;
                        }
                    }
                    // After ±1 clamp, re-assert we did not dig under land grade.
                    if (trail && !bridge && !columns[i].isCrossing()
                            && y < columns[i].surfaceY()) {
                        int prev = i > 0 ? chunkProfile[i - 1]
                                : (index > 0 ? profile[index - 1] : startY);
                        y = Math.min(columns[i].surfaceY(), prev + BridgeSpan.MAX_STEP);
                        if (y < columns[i].surfaceY() && y < prev + BridgeSpan.MAX_STEP) {
                            y = prev + BridgeSpan.MAX_STEP;
                        }
                    }
                    chunkProfile[i] = y;
                    profile[index + i] = y;
                }
                index += line.length;

                CorridorChunk chunk = planCorridorChunk(
                        world, line, columns, chunkProfile,
                        right, half, width, trail || bridge, clearSite
                );
                probe.totalSteps += line.length;
                if (chunk.needsBuildClear) {
                    probe.needsBuildClear = true;
                }
                if (!apply) {
                    if (probe.needsBuildClear) {
                        return probe;
                    }
                    continue;
                }
                if (chunk.surface.isEmpty()) {
                    continue;
                }
                for (Block block : chunk.surface) {
                    if (block.getX() == px && block.getZ() == pz
                            && block.getY() >= py && block.getY() <= py + 1) {
                        probe.denied = "You're in the way — step back and try again.";
                        return probe;
                    }
                }
                List<Location> locations = new ArrayList<>(chunk.surface.size() + chunk.clear.size());
                for (Block block : chunk.surface) {
                    locations.add(block.getLocation());
                }
                for (Block block : chunk.clear) {
                    locations.add(block.getLocation());
                }
                String denied = buildPolicy.denyReason(player, locations, material);
                if (denied != null) {
                    probe.denied = denied;
                    return probe;
                }
                try {
                    Runnable undo = BoundedFaweEdit.applyMixed(
                            world, player.getUniqueId(), chunk.surface, material, chunk.clear
                    );
                    boolean verified = chunk.surface.stream()
                            .allMatch(block -> block.getType() == material);
                    if (!verified) {
                        undo.run();
                        probe.denied = "I couldn't place that exactly, so I put things back.";
                        return probe;
                    }
                    undos.add(undo);
                    probe.chunksApplied++;
                } catch (RuntimeException error) {
                    probe.denied = "I couldn't place that exactly, so I put things back.";
                    return probe;
                }
            }
        }
        return probe;
    }

    private CorridorChunk planCorridorChunk(
            World world,
            int[][] line,
            BridgeSpan.Column[] columns,
            int[] profile,
            Vector right,
            int half,
            int width,
            boolean clearHeadroom,
            boolean clearSite
    ) {
        List<Block> surface = new ArrayList<>(line.length * width);
        List<Block> clearBlocks = new ArrayList<>();
        boolean needsBuildClear = false;
        for (int i = 0; i < line.length; i++) {
            int cx = line[i][0];
            int cz = line[i][1];
            int y = profile[i];
            BridgeSpan.Column col = columns[i];
            // Never place a trail under sampled land grade (trench + grass lids).
            if (!col.isCrossing() && y < col.surfaceY()) {
                y = col.surfaceY();
            }
            for (int w = 0; w < width; w++) {
                int lateral = w - half;
                int bx = cx + right.getBlockX() * lateral;
                int bz = cz + right.getBlockZ() * lateral;
                int localY = y;
                if (!col.isCrossing()) {
                    int localWalk = walkSurfaceY(world, bx, Math.max(y, col.surfaceY()), bz);
                    localY = Math.max(y, localWalk);
                }
                Block surfaceBlock = world.getBlockAt(bx, localY, bz);
                surface.add(surfaceBlock);
                if (!clearHeadroom) {
                    continue;
                }
                for (int dy = 1; dy <= PATH_HEADROOM; dy++) {
                    Block above = world.getBlockAt(bx, localY + dy, bz);
                    Material mat = above.getType();
                    if (mat.isAir()) {
                        continue;
                    }
                    if (isSoftClearable(mat)) {
                        clearBlocks.add(above);
                    } else if (mat.isSolid() && !isWater(mat)) {
                        if (markerSessions != null && mat == markerSessions.markerBlock()) {
                            clearBlocks.add(above);
                        } else if (NativeSchematicPaster.isNaturalTerrain(mat)) {
                            // Surface-follow paths — never excavate natural ground.
                            continue;
                        } else {
                            needsBuildClear = true;
                            if (clearSite) {
                                clearBlocks.add(above);
                            }
                        }
                    }
                }
            }
        }
        if (wouldOverwriteBuilds(surface, true)) {
            needsBuildClear = true;
        }
        Set<String> surfaceKeys = new HashSet<>();
        for (Block block : surface) {
            surfaceKeys.add(block.getX() + "," + block.getY() + "," + block.getZ());
        }
        Set<String> seen = new HashSet<>();
        List<Block> allClear = new ArrayList<>();
        for (Block block : clearBlocks) {
            String key = block.getX() + "," + block.getY() + "," + block.getZ();
            if (surfaceKeys.contains(key) || !seen.add(key)) {
                continue;
            }
            allClear.add(block);
        }
        int nextSeed = profile.length == 0 ? 0 : profile[profile.length - 1];
        return new CorridorChunk(surface, allClear, needsBuildClear, nextSeed);
    }

    /** Marker block Y if it is the walk surface; otherwise support under the band. */
    private static int preferMarkerWalkY(World world, PathMarkerSessions.BlockPos marker) {
        Block block = world.getBlockAt(marker.x(), marker.y(), marker.z());
        if (block.getType().isSolid()) {
            return marker.y();
        }
        return walkSurfaceY(world, marker.x(), marker.y() + 1, marker.z());
    }

    /** Vegetation, leaves, logs, water plants — fine to clear for a trail. */
    private static boolean isSoftClearable(Material mat) {
        if (mat.isAir() || isWater(mat) || isWaterPlant(mat)) {
            return true;
        }
        return org.bukkit.Tag.LEAVES.isTagged(mat)
                || org.bukkit.Tag.LOGS.isTagged(mat)
                || org.bukkit.Tag.SAPLINGS.isTagged(mat)
                || org.bukkit.Tag.FLOWERS.isTagged(mat)
                || org.bukkit.Tag.REPLACEABLE.isTagged(mat)
                || mat == Material.SNOW
                || mat == Material.MOSS_CARPET
                || mat == Material.VINE
                || mat == Material.GLOW_LICHEN
                || mat == Material.COBWEB;
    }

    /**
     * True when surface placement would wipe non-natural builds (not dirt/grass
     * path cover, not water plants).
     */
    private static boolean wouldOverwriteBuilds(List<Block> blocks, boolean allowWaterPlants) {
        for (Block block : blocks) {
            Material mat = block.getType();
            if (mat.isAir()) {
                continue;
            }
            if (allowWaterPlants && (isWater(mat) || isWaterPlant(mat))) {
                continue;
            }
            if (isFlatGroundCover(mat) || isSoftClearable(mat)
                    || NativeSchematicPaster.isNaturalTerrain(mat)) {
                continue;
            }
            if (mat.isSolid()) {
                return true;
            }
        }
        return false;
    }

    private ToolResult applyCorridor(
            Player player,
            List<Block> surface,
            List<Block> clearBlocks,
            Material material,
            long started,
            String okMessage,
            boolean allowWaterPlants
    ) {
        return applyCorridorChunked(
                player, surface, clearBlocks, material, 1, started, okMessage
        );
    }

    /**
     * Apply a corridor in FAWE chunks of roughly {@link BridgeSpan#MAX_LENGTH}
     * centerline steps (× width surface cells). One undo rolls back every chunk.
     */
    private ToolResult applyCorridorChunked(
            Player player,
            List<Block> surface,
            List<Block> clearBlocks,
            Material material,
            int width,
            long started,
            String okMessage
    ) {
        if (surface.isEmpty()) {
            return ToolResult.fail("I couldn't find a clear spot for that.", elapsed(started));
        }
        int px = player.getLocation().getBlockX();
        int pz = player.getLocation().getBlockZ();
        int py = player.getLocation().getBlockY();
        for (Block block : surface) {
            if (block.getX() == px && block.getZ() == pz
                    && block.getY() >= py && block.getY() <= py + 1) {
                return ToolResult.fail(
                        "You're in the way — step back and try again.",
                        elapsed(started)
                );
            }
        }
        List<Location> locations = new ArrayList<>();
        for (Block block : surface) {
            locations.add(block.getLocation());
        }
        for (Block block : clearBlocks) {
            locations.add(block.getLocation());
        }
        String denied = buildPolicy.denyReason(player, locations, material);
        if (denied != null) {
            return ToolResult.fail(denied, elapsed(started));
        }

        int cellsPerChunk = Math.max(width, 1) * BridgeSpan.MAX_LENGTH;
        List<List<Block>> surfaceChunks = partitionBlocks(surface, cellsPerChunk);
        List<List<Block>> clearChunks = partitionClears(clearBlocks, surfaceChunks);
        List<Runnable> undos = new ArrayList<>();
        World world = player.getWorld();
        try {
            for (int i = 0; i < surfaceChunks.size(); i++) {
                List<Block> chunkSurface = surfaceChunks.get(i);
                List<Block> chunkClear = i < clearChunks.size() ? clearChunks.get(i) : List.of();
                undos.add(BoundedFaweEdit.applyMixed(
                        world, player.getUniqueId(), chunkSurface, material, chunkClear
                ));
            }
        } catch (RuntimeException error) {
            rollbackAll(undos);
            return ToolResult.fail("I couldn't place that exactly, so I put things back.", elapsed(started));
        }
        boolean verified = surface.stream().allMatch(block -> block.getType() == material);
        if (!verified) {
            rollbackAll(undos);
            return ToolResult.fail("I couldn't place that exactly, so I put things back.", elapsed(started));
        }
        rememberUndo.accept(player, () -> rollbackAll(undos));
        return ToolResult.ok(
                okMessage + " Say “undo that” if you don’t like it.",
                true,
                elapsed(started)
        );
    }

    private static List<List<Block>> partitionBlocks(List<Block> blocks, int chunkSize) {
        List<List<Block>> chunks = new ArrayList<>();
        if (blocks.isEmpty()) {
            return chunks;
        }
        int size = Math.max(1, chunkSize);
        for (int i = 0; i < blocks.size(); i += size) {
            chunks.add(new ArrayList<>(blocks.subList(i, Math.min(blocks.size(), i + size))));
        }
        return chunks;
    }

    /**
     * Attach clears to the surface chunk whose bounding box contains them;
     * leftovers go on the last chunk.
     */
    private static List<List<Block>> partitionClears(
            List<Block> clearBlocks, List<List<Block>> surfaceChunks
    ) {
        List<List<Block>> clearChunks = new ArrayList<>();
        for (int i = 0; i < surfaceChunks.size(); i++) {
            clearChunks.add(new ArrayList<>());
        }
        if (clearBlocks.isEmpty() || surfaceChunks.isEmpty()) {
            return clearChunks;
        }
        for (Block clear : clearBlocks) {
            int best = surfaceChunks.size() - 1;
            for (int i = 0; i < surfaceChunks.size(); i++) {
                if (nearChunk(clear, surfaceChunks.get(i))) {
                    best = i;
                    break;
                }
            }
            clearChunks.get(best).add(clear);
        }
        return clearChunks;
    }

    private static boolean nearChunk(Block clear, List<Block> chunk) {
        for (Block block : chunk) {
            if (block.getX() == clear.getX() && block.getZ() == clear.getZ()
                    && Math.abs(block.getY() - clear.getY()) <= PATH_HEADROOM + 4) {
                return true;
            }
        }
        return false;
    }

    private static void rollbackAll(List<Runnable> undos) {
        List<Runnable> reverse = new ArrayList<>(undos);
        Collections.reverse(reverse);
        for (Runnable undo : reverse) {
            try {
                undo.run();
            } catch (RuntimeException ignored) {
                // best-effort rollback
            }
        }
    }

    /**
     * Classify one column for bridge/road spanning. Scans down from the
     * player band so elevated standpoints still see ocean water below.
     */
    static BridgeSpan.Column sampleColumn(World world, int x, int z, int nearY) {
        int maxScan = Math.min(world.getMaxHeight() - 1, nearY + 8);
        int minScan = Math.max(world.getMinHeight(), nearY - 64);
        Integer waterTop = null;
        Integer solidTop = null;
        for (int y = maxScan; y >= minScan; y--) {
            Material mat = world.getBlockAt(x, y, z).getType();
            if (isWater(mat) || isWaterPlant(mat)) {
                if (waterTop == null) {
                    waterTop = y;
                }
                continue;
            }
            if (isLava(mat)) {
                return BridgeSpan.Column.lava(y);
            }
            if (mat.isAir() || isPassableNonSolid(mat)) {
                if (waterTop != null) {
                    int solid = solidTop != null ? solidTop : waterTop - 1;
                    return BridgeSpan.Column.water(waterTop, solid);
                }
                continue;
            }
            if (mat.isSolid()) {
                if (waterTop != null) {
                    return BridgeSpan.Column.water(waterTop, y);
                }
                // If the scan started inside solid (nearY too low), climb to the
                // real surface so stairs don't hug an underground false grade.
                solidTop = riseToSolidSurface(world, x, z, y);
                // Solid near the player band → land. Deep solid under open air → gap.
                if (solidTop >= nearY - 12) {
                    return BridgeSpan.Column.land(solidTop);
                }
                return BridgeSpan.Column.gap(Math.max(minScan, nearY - 1));
            }
        }
        if (waterTop != null) {
            return BridgeSpan.Column.water(waterTop, waterTop - 1);
        }
        if (solidTop != null) {
            return BridgeSpan.Column.land(solidTop);
        }
        return BridgeSpan.Column.gap(Math.max(minScan, nearY - 1));
    }

    /**
     * When a downward scan begins inside a solid column, walk up to the topmost
     * contiguous solid so the reported surface is outdoor grade — not a cave
     * ceiling or buried dirt layer.
     */
    private static int riseToSolidSurface(World world, int x, int z, int startSolidY) {
        int y = startSolidY;
        int max = world.getMaxHeight() - 1;
        while (y < max) {
            Material above = world.getBlockAt(x, y + 1, z).getType();
            if (!above.isSolid() || isWater(above) || isLava(above)) {
                break;
            }
            if (isPassableNonSolid(above)) {
                break;
            }
            y++;
        }
        return y;
    }

    private static boolean isWater(Material mat) {
        return mat == Material.WATER
                || mat == Material.BUBBLE_COLUMN
                || mat.name().endsWith("_WATER");
    }

    private static boolean isLava(Material mat) {
        return mat == Material.LAVA;
    }

    private static boolean isWaterPlant(Material mat) {
        return mat == Material.KELP
                || mat == Material.KELP_PLANT
                || mat == Material.SEAGRASS
                || mat == Material.TALL_SEAGRASS
                || mat == Material.SEA_PICKLE;
    }

    private static boolean isPassableNonSolid(Material mat) {
        return org.bukkit.Tag.REPLACEABLE.isTagged(mat)
                || mat == Material.SNOW
                || mat == Material.MOSS_CARPET;
    }

    private ToolResult placeWall(
            Player player, JsonObject args, Material material, long started, boolean clearSite
    ) {
        int length = clamp(optionalInt(args, "length", 8), 2, 48);
        int height = clamp(optionalInt(args, "height", 4), 1, 32);
        if (length * height > MAX_WALL_CELLS) {
            return ToolResult.fail("That wall is too big. Try a smaller size.", elapsed(started));
        }
        Vector forward = horizontalForward(player);
        // Right-hand horizontal: up × forward → (fz, 0, -fx).
        Vector right = new Vector(forward.getZ(), 0, -forward.getX());
        Location origin = player.getLocation().getBlock().getLocation().add(forward.clone().multiply(3));
        // Center wall on facing axis.
        int start = -(length / 2);
        World world = player.getWorld();
        List<Block> blocks = new ArrayList<>();
        for (int i = 0; i < length; i++) {
            Vector offset = right.clone().multiply(start + i);
            int bx = origin.getBlockX() + offset.getBlockX();
            int bz = origin.getBlockZ() + offset.getBlockZ();
            int baseY = supportY(world, bx, origin.getBlockY(), bz);
            for (int y = 0; y < height; y++) {
                blocks.add(world.getBlockAt(bx, baseY + 1 + y, bz));
            }
        }
        return apply(player, blocks, material, started, clearSite,
                "Built a " + readable(material) + " wall (" + length + " long, " + height + " tall).",
                false);
    }

    private ToolResult placePlatform(
            Player player, JsonObject args, Material material, long started, boolean clearSite
    ) {
        int width = clamp(optionalInt(args, "width", 5), 1, 32);
        int depth = clamp(optionalInt(args, "depth", width), 1, 32);
        if (width * depth > MAX_PLATFORM_CELLS) {
            return ToolResult.fail("That platform is too big. Try up to 32×32.", elapsed(started));
        }
        Vector forward = horizontalForward(player);
        Location feet = player.getLocation().getBlock().getLocation();
        int originX;
        int originZ;
        if (Math.abs(forward.getX()) >= Math.abs(forward.getZ())) {
            originZ = feet.getBlockZ() - (depth / 2);
            originX = feet.getBlockX() + (forward.getX() >= 0 ? 2 : -width - 1);
        } else {
            originX = feet.getBlockX() - (width / 2);
            originZ = feet.getBlockZ() + (forward.getZ() >= 0 ? 2 : -depth - 1);
        }
        World world = player.getWorld();
        int y = supportY(world, feet.getBlockX(), feet.getBlockY(), feet.getBlockZ());
        List<Block> blocks = new ArrayList<>();
        for (int x = 0; x < width; x++) {
            for (int z = 0; z < depth; z++) {
                blocks.add(world.getBlockAt(originX + x, y, originZ + z));
            }
        }
        return apply(player, blocks, material, started, clearSite,
                "Built a " + width + "×" + depth + " " + readable(material) + " platform.",
                false);
    }

    private ToolResult placeBox(
            Player player,
            JsonObject args,
            Material material,
            long started,
            boolean solid,
            boolean clearSite
    ) {
        // Footprint up to 32×32 matches platform budget; height stays ≤24.
        int width = clamp(optionalInt(args, "width", 5), 3, 32);
        int depth = clamp(optionalInt(args, "depth", width), 3, 32);
        int height = clamp(optionalInt(args, "height", 4), 2, 24);
        boolean roof = !args.has("roof") || args.get("roof").getAsBoolean();
        Vector forward = horizontalForward(player);
        Location feet = player.getLocation().getBlock().getLocation();
        int minX;
        int minZ;
        if (Math.abs(forward.getX()) >= Math.abs(forward.getZ())) {
            minX = feet.getBlockX() + (forward.getX() >= 0 ? 2 : -width - 1);
            minZ = feet.getBlockZ() - (depth / 2);
        } else {
            minX = feet.getBlockX() - (width / 2);
            minZ = feet.getBlockZ() + (forward.getZ() >= 0 ? 2 : -depth - 1);
        }
        World world = player.getWorld();
        int minY = supportY(world, feet.getBlockX(), feet.getBlockY(), feet.getBlockZ()) + 1;
        int maxX = minX + width - 1;
        int maxZ = minZ + depth - 1;
        int maxY = minY + height - 1;
        List<Block> blocks = new ArrayList<>();
        for (int x = minX; x <= maxX; x++) {
            for (int y = minY; y <= maxY; y++) {
                for (int z = minZ; z <= maxZ; z++) {
                    boolean wall = x == minX || x == maxX || z == minZ || z == maxZ;
                    boolean isRoof = roof && y == maxY;
                    if (solid || wall || isRoof) {
                        blocks.add(world.getBlockAt(x, y, z));
                    }
                }
            }
        }
        int cap = solid ? MAX_SOLID_CELLS : MAX_OUTLINE_CELLS;
        if (blocks.size() > cap) {
            return ToolResult.fail("That box is too big. Try a smaller size.", elapsed(started));
        }
        String label = solid ? "solid box" : (roof ? "box" : "enclosure");
        return apply(player, blocks, material, started, clearSite,
                "Built a " + width + "×" + depth + "×" + height + " " + readable(material) + " " + label + ".",
                false);
    }

    private ToolResult placeCylinder(
            Player player, JsonObject args, Material material, long started, boolean clearSite
    ) {
        int diameter = clamp(optionalInt(args, "width", 6), 2, 32);
        int height = clamp(optionalInt(args, "height", 8), 1, 32);
        int radius = Math.max(1, diameter / 2);
        Vector forward = horizontalForward(player);
        Location feet = player.getLocation().getBlock().getLocation();
        int cx = feet.getBlockX() + forward.getBlockX() * (radius + 2);
        int cz = feet.getBlockZ() + forward.getBlockZ() * (radius + 2);
        World world = player.getWorld();
        int baseY = supportY(world, feet.getBlockX(), feet.getBlockY(), feet.getBlockZ()) + 1;
        List<Block> blocks = new ArrayList<>();
        for (int y = 0; y < height; y++) {
            for (int x = -radius; x <= radius; x++) {
                for (int z = -radius; z <= radius; z++) {
                    if (x * x + z * z <= radius * radius) {
                        blocks.add(world.getBlockAt(cx + x, baseY + y, cz + z));
                    }
                }
            }
        }
        if (blocks.size() > MAX_SOLID_CELLS) {
            return ToolResult.fail("That cylinder is too big. Try a smaller size.", elapsed(started));
        }
        return apply(player, blocks, material, started, clearSite,
                "Built a " + readable(material) + " cylinder (" + height + " tall).",
                false);
    }

    private ToolResult apply(
            Player player,
            List<Block> blocks,
            Material material,
            long started,
            boolean clearSite,
            String okMessage,
            boolean allowWaterPlants
    ) {
        if (blocks.isEmpty()) {
            return ToolResult.fail("I couldn't find a clear spot for that.", elapsed(started));
        }
        // Refuse overlapping the player's column.
        int px = player.getLocation().getBlockX();
        int pz = player.getLocation().getBlockZ();
        int py = player.getLocation().getBlockY();
        for (Block block : blocks) {
            if (block.getX() == px && block.getZ() == pz
                    && block.getY() >= py && block.getY() <= py + 1) {
                return ToolResult.fail(
                        "You're in the way — step back and try again.",
                        elapsed(started)
                );
            }
        }
        // Ask before overwriting existing solids (trees/builds in the way).
        // Water plants are fine to clear when spanning a bridge/road.
        if (!clearSite && wouldOverwriteSolids(blocks, allowWaterPlants)) {
            return ToolResult.fail(SchematicPlacement.CLEAR_ASK_MESSAGE, elapsed(started));
        }
        List<Location> locations = blocks.stream().map(Block::getLocation).toList();
        String denied = buildPolicy.denyReason(player, locations, material);
        if (denied != null) {
            return ToolResult.fail(denied, elapsed(started));
        }
        Runnable undo = BoundedFaweEdit.apply(
                player.getWorld(), player.getUniqueId(), blocks, material
        );
        boolean verified = blocks.stream().allMatch(block -> block.getType() == material);
        if (!verified) {
            undo.run();
            return ToolResult.fail("I couldn't place that exactly, so I put things back.", elapsed(started));
        }
        rememberUndo.accept(player, undo);
        return ToolResult.ok(
                okMessage + " Say “undo that” if you don’t like it.",
                true,
                elapsed(started)
        );
    }

    /**
     * True when placement would wipe trees/builds/debris. Replacing a flat
     * ground layer (grass/dirt under a platform) does not count. Water and
     * water plants are ignored when {@code allowWaterPlants} is true.
     */
    private static boolean wouldOverwriteSolids(List<Block> blocks, boolean allowWaterPlants) {
        int minY = Integer.MAX_VALUE;
        for (Block block : blocks) {
            minY = Math.min(minY, block.getY());
        }
        for (Block block : blocks) {
            Material mat = block.getType();
            if (mat.isAir()) {
                continue;
            }
            if (allowWaterPlants && (isWater(mat) || isWaterPlant(mat))) {
                continue;
            }
            if (block.getY() == minY && isFlatGroundCover(mat)) {
                continue;
            }
            if (mat.isSolid()
                    || org.bukkit.Tag.LEAVES.isTagged(mat)
                    || org.bukkit.Tag.LOGS.isTagged(mat)
                    || org.bukkit.Tag.REPLACEABLE.isTagged(mat)) {
                return true;
            }
        }
        return false;
    }

    private static boolean isFlatGroundCover(Material mat) {
        return NativeSchematicPaster.isNaturalTerrain(mat)
                && mat.isSolid()
                && !org.bukkit.Tag.LEAVES.isTagged(mat)
                && !org.bukkit.Tag.LOGS.isTagged(mat);
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

    private static Material resolveMaterial(Player player, String requested) {
        if (requested != null && !requested.isBlank()) {
            String key = requested.toLowerCase(Locale.ROOT).replace("minecraft:", "");
            Material material = Material.matchMaterial(key);
            if (material != null && material.isBlock() && !material.isAir()) {
                return material;
            }
            // Explicit material was requested but is not a placeable block —
            // do not silently fall back to the held item (that caused dirt
            // platforms when routing sent oak_platform / stone_box).
            return null;
        }
        var hand = player.getInventory().getItemInMainHand();
        if (hand != null && hand.getType().isBlock() && !hand.getType().isAir()) {
            return hand.getType();
        }
        return null;
    }

    private static Vector horizontalForward(Player player) {
        Vector direction = player.getLocation().getDirection();
        direction.setY(0);
        if (direction.lengthSquared() < 1.0e-6) {
            return new Vector(0, 0, 1);
        }
        direction.normalize();
        // Snap to cardinal for clean builds.
        if (Math.abs(direction.getX()) >= Math.abs(direction.getZ())) {
            return new Vector(direction.getX() >= 0 ? 1 : -1, 0, 0);
        }
        return new Vector(0, 0, direction.getZ() >= 0 ? 1 : -1);
    }

    /**
     * Walk surface near the feet/seed band. Scans only a few blocks below
     * {@code nearY} so elevated piers stay at plank height and open water does
     * not snap to the lakebed (the stairs-to-door "start too deep" bug).
     */
    private static int walkSurfaceY(World world, int x, int nearY, int z) {
        int top = Math.min(nearY + 2, world.getMaxHeight() - 2);
        int floor = Math.max(world.getMinHeight(), nearY - 4);
        Integer waterTop = null;
        Integer solidTop = null;
        for (int y = top; y >= floor; y--) {
            Material mat = world.getBlockAt(x, y, z).getType();
            if (isWater(mat) || isLava(mat) || isWaterPlant(mat)) {
                if (waterTop == null && isWater(mat)) {
                    waterTop = y;
                }
                continue;
            }
            if (mat.isAir() || isPassableNonSolid(mat)) {
                continue;
            }
            if (mat.isSolid()) {
                solidTop = y;
                break;
            }
        }
        if (solidTop != null) {
            return BridgeSpan.preferWalkSurface(nearY, solidTop, waterTop, 4);
        }
        if (waterTop != null) {
            return Math.max(waterTop, nearY - 1);
        }
        return Math.max(world.getMinHeight(), nearY - 1);
    }

    private static int supportY(World world, int x, int nearY, int z) {
        // Prefer the shallow walk surface first (pier / path top).
        int walk = walkSurfaceY(world, x, nearY, z);
        Block walkBlock = world.getBlockAt(x, walk, z);
        if (walkBlock.getType().isSolid() && !isWater(walkBlock.getType())) {
            return walk;
        }
        int y = Math.min(nearY + 2, world.getMaxHeight() - 2);
        int min = world.getMinHeight();
        while (y > min) {
            Block block = world.getBlockAt(x, y, z);
            Material mat = block.getType();
            if (isWater(mat) || isLava(mat)) {
                // Do not fall through water to lakebed for generic support.
                return Math.max(walk, Math.max(y, nearY - 1));
            }
            if (!mat.isAir() && mat.isSolid()) {
                return BridgeSpan.preferWalkSurface(nearY, y, null, 12);
            }
            y--;
        }
        return Math.max(min, nearY - 1);
    }

    private static String readable(Material material) {
        return material.getKey().getKey().replace('_', ' ');
    }

    private static int clamp(int value, int min, int max) {
        return Math.max(min, Math.min(max, value));
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

    private static int elapsed(long started) {
        return (int) ((System.nanoTime() - started) / 1_000_000L);
    }
}
