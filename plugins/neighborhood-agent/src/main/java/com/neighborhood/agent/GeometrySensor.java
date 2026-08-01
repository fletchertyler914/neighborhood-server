package com.neighborhood.agent;

import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.block.BlockFace;
import org.bukkit.entity.Player;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

record OpeningFacet(
        String axis,
        int minX,
        int maxX,
        int minY,
        int maxY,
        int minZ,
        int maxZ,
        int length,
        int height,
        int airCells,
        String endAMaterial,
        String endBMaterial,
        String suggestedMaterial,
        String confidence
) {
}

record SurfaceFacet(
        String axis,
        String normal,
        int minX,
        int maxX,
        int minY,
        int maxY,
        int minZ,
        int maxZ,
        int width,
        int height,
        String material,
        String confidence
) {
}

record ClearanceFacet(
        int minX,
        int maxX,
        int minY,
        int maxY,
        int minZ,
        int maxZ,
        int width,
        int height,
        int depth,
        int airCells,
        String confidence
) {
}

record PaletteEntry(String material, int count) {
}

record FloorFacet(
        int minX,
        int maxX,
        int y,
        int minZ,
        int maxZ,
        int width,
        int depth,
        int airCells,
        String confidence
) {
}

record GeometryResult(
        SurfaceFacet surface,
        List<OpeningFacet> openings,
        ClearanceFacet clearance,
        List<PaletteEntry> palette,
        String fingerprint,
        String confidence,
        PerceptionBudget budget
) {
}

final class GeometrySensor {
    private GeometrySensor() {
    }

    static FloorFacet findFloor(Player player, GazeHit gaze) {
        return findFloor(player, gaze, true);
    }

    /**
     * @param preferSolid when false, only detect open air floor planes (fill mode).
     *                    when true, prefer solid walkable floors (replace/clear),
     *                    then fall back to an air plane for mixed rooms.
     */
    static FloorFacet findFloor(Player player, GazeHit gaze, boolean preferSolid) {
        if (!preferSolid) {
            return findAirFloor(player, gaze);
        }
        FloorFacet solid = findSolidFloor(player, gaze);
        if (solid != null) {
            return solid;
        }
        return findAirFloor(player, gaze);
    }

    private static FloorFacet findAirFloor(Player player, GazeHit gaze) {
        PerceptionBudget budget = new PerceptionBudget();
        Block seed = resolveAirFloorSeed(player, gaze, budget);
        if (seed == null || isSolid(seed)) {
            return null;
        }
        World world = seed.getWorld();
        int y = seed.getY();
        int minX = seed.getX();
        int maxX = seed.getX();
        int minZ = seed.getZ();
        int maxZ = seed.getZ();
        boolean grew = true;
        int guard = 0;
        while (grew && guard++ < PerceptionBudget.MAX_OPENING_LENGTH) {
            grew = false;
            if (canGrowAirFloorStrip(world, minX - 1, minX - 1, minZ, maxZ, y, budget)) {
                minX--;
                grew = true;
            }
            if (canGrowAirFloorStrip(world, maxX + 1, maxX + 1, minZ, maxZ, y, budget)) {
                maxX++;
                grew = true;
            }
            if (canGrowAirFloorStrip(world, minX, maxX, minZ - 1, minZ - 1, y, budget)) {
                minZ--;
                grew = true;
            }
            if (canGrowAirFloorStrip(world, minX, maxX, maxZ + 1, maxZ + 1, y, budget)) {
                maxZ++;
                grew = true;
            }
            int width = maxX - minX + 1;
            int depth = maxZ - minZ + 1;
            if (width > PerceptionBudget.MAX_OPENING_LENGTH || depth > PerceptionBudget.MAX_OPENING_LENGTH) {
                return null;
            }
        }
        return finalizeFloorFacet(world, minX, maxX, minZ, maxZ, y, budget, true);
    }

    private static FloorFacet findSolidFloor(Player player, GazeHit gaze) {
        PerceptionBudget budget = new PerceptionBudget();
        Block seed = resolveSolidFloorSeed(player, gaze, budget);
        if (seed == null || !isSolid(seed) || !isWalkableFloorCell(seed)) {
            return null;
        }
        World world = seed.getWorld();
        Material expected = seed.getType();
        int y = seed.getY();
        int minX = seed.getX();
        int maxX = seed.getX();
        int minZ = seed.getZ();
        int maxZ = seed.getZ();
        boolean grew = true;
        int guard = 0;
        while (grew && guard++ < PerceptionBudget.MAX_OPENING_LENGTH) {
            grew = false;
            if (canGrowSolidFloorStrip(world, minX - 1, minX - 1, minZ, maxZ, y, expected, budget)) {
                minX--;
                grew = true;
            }
            if (canGrowSolidFloorStrip(world, maxX + 1, maxX + 1, minZ, maxZ, y, expected, budget)) {
                maxX++;
                grew = true;
            }
            if (canGrowSolidFloorStrip(world, minX, maxX, minZ - 1, minZ - 1, y, expected, budget)) {
                minZ--;
                grew = true;
            }
            if (canGrowSolidFloorStrip(world, minX, maxX, maxZ + 1, maxZ + 1, y, expected, budget)) {
                maxZ++;
                grew = true;
            }
            int width = maxX - minX + 1;
            int depth = maxZ - minZ + 1;
            if (width > PerceptionBudget.MAX_OPENING_LENGTH || depth > PerceptionBudget.MAX_OPENING_LENGTH) {
                return null;
            }
        }
        return finalizeFloorFacet(world, minX, maxX, minZ, maxZ, y, budget, false);
    }

    private static FloorFacet finalizeFloorFacet(
            World world,
            int minX,
            int maxX,
            int minZ,
            int maxZ,
            int y,
            PerceptionBudget budget,
            boolean requireAir
    ) {
        int width = maxX - minX + 1;
        int depth = maxZ - minZ + 1;
        if (width < 2 || depth < 2) {
            return null;
        }
        int airCells = 0;
        int solidCells = 0;
        for (int x = minX; x <= maxX; x++) {
            for (int z = minZ; z <= maxZ; z++) {
                budget.sampleCell();
                if (!isSolid(world.getBlockAt(x, y, z))) {
                    airCells++;
                } else {
                    solidCells++;
                }
            }
        }
        if (requireAir && airCells == 0) {
            return null;
        }
        if (!requireAir && solidCells == 0) {
            return null;
        }
        int walled = countFloorWalls(world, minX, maxX, minZ, maxZ, y);
        if (walled < 3) {
            return null;
        }
        int scored = requireAir ? airCells : solidCells;
        String confidence = scored >= 8 && walled >= 4 ? "high" : "medium";
        return new FloorFacet(minX, maxX, y, minZ, maxZ, width, depth, airCells, confidence);
    }

    private static Block resolveAirFloorSeed(Player player, GazeHit gaze, PerceptionBudget budget) {
        if (gaze.hit() && gaze.block() != null) {
            Block hit = gaze.block();
            if (gaze.face() == BlockFace.UP && isSolid(hit)) {
                Block above = hit.getRelative(BlockFace.UP);
                if (!isSolid(above)) {
                    return above;
                }
            }
            if (!isSolid(hit)) {
                return hit;
            }
            Block above = hit.getRelative(BlockFace.UP);
            if (!isSolid(above)) {
                return above;
            }
        }
        Block feet = player.getLocation().getBlock();
        budget.sampleCell();
        if (!isSolid(feet)) {
            return feet;
        }
        Block above = feet.getRelative(BlockFace.UP);
        return isSolid(above) ? null : above;
    }

    private static Block resolveSolidFloorSeed(Player player, GazeHit gaze, PerceptionBudget budget) {
        if (gaze.hit() && gaze.block() != null) {
            Block hit = gaze.block();
            if (isSolid(hit) && isWalkableFloorCell(hit)) {
                return hit;
            }
            if (gaze.face() == BlockFace.UP && isSolid(hit) && isWalkableFloorCell(hit)) {
                return hit;
            }
        }
        Block underFeet = player.getLocation().getBlock().getRelative(BlockFace.DOWN);
        budget.sampleCell();
        if (isSolid(underFeet) && isWalkableFloorCell(underFeet)) {
            return underFeet;
        }
        return null;
    }

    private static boolean isWalkableFloorCell(Block block) {
        // Wall columns usually continue upward; floor cells have air above.
        return !isSolid(block.getRelative(BlockFace.UP));
    }

    private static boolean canGrowAirFloorStrip(
            World world,
            int minX,
            int maxX,
            int minZ,
            int maxZ,
            int y,
            PerceptionBudget budget
    ) {
        for (int x = minX; x <= maxX; x++) {
            for (int z = minZ; z <= maxZ; z++) {
                if (!budget.sampleCell()) {
                    return false;
                }
                if (isSolid(world.getBlockAt(x, y, z))) {
                    return false;
                }
            }
        }
        return true;
    }

    private static boolean canGrowSolidFloorStrip(
            World world,
            int minX,
            int maxX,
            int minZ,
            int maxZ,
            int y,
            Material expected,
            PerceptionBudget budget
    ) {
        for (int x = minX; x <= maxX; x++) {
            for (int z = minZ; z <= maxZ; z++) {
                if (!budget.sampleCell()) {
                    return false;
                }
                Block block = world.getBlockAt(x, y, z);
                if (!isSolid(block) || block.getType() != expected || !isWalkableFloorCell(block)) {
                    return false;
                }
            }
        }
        return true;
    }

    private static int countFloorWalls(
            World world,
            int minX,
            int maxX,
            int minZ,
            int maxZ,
            int y
    ) {
        int sides = 0;
        if (floorSideWalled(world, minX - 1, minX - 1, minZ, maxZ, y)) {
            sides++;
        }
        if (floorSideWalled(world, maxX + 1, maxX + 1, minZ, maxZ, y)) {
            sides++;
        }
        if (floorSideWalled(world, minX, maxX, minZ - 1, minZ - 1, y)) {
            sides++;
        }
        if (floorSideWalled(world, minX, maxX, maxZ + 1, maxZ + 1, y)) {
            sides++;
        }
        return sides;
    }

    private static boolean floorSideWalled(
            World world,
            int minX,
            int maxX,
            int minZ,
            int maxZ,
            int y
    ) {
        int solid = 0;
        int total = 0;
        for (int x = minX; x <= maxX; x++) {
            for (int z = minZ; z <= maxZ; z++) {
                total++;
                // Walls may sit on the same Y or one above the floor air layer.
                if (isSolid(world.getBlockAt(x, y, z)) || isSolid(world.getBlockAt(x, y + 1, z))) {
                    solid++;
                }
            }
        }
        return total > 0 && solid * 100 / total >= 50;
    }

    static GeometryResult inspect(Player player, GazeHit gaze, String purpose, String heldMaterial) {
        PerceptionBudget budget = new PerceptionBudget();
        World world = player.getWorld();
        Block anchor = resolveAnchor(player, gaze, budget);
        List<OpeningFacet> openings = findOpenings(player, anchor, gaze, heldMaterial, budget);
        openings = preferExteriorOpenings(player, openings);
        SurfaceFacet surface = surfaceFromGaze(gaze, openings);
        ClearanceFacet clearance = "paste_template".equals(purpose)
                ? clearanceAhead(player, gaze, budget)
                : null;
        // Skip palette for wall/floor finish — geometry already dominates the tick budget.
        List<PaletteEntry> palette = ("finish_wall".equals(purpose) || "finish_floor".equals(purpose))
                ? List.of()
                : samplePalette(world, anchor, budget);
        OpeningFacet best = openings.isEmpty() ? null : openings.get(0);
        String fingerprint = best == null
                ? SceneFingerprint.fast(player, gaze.block(), gaze.face(), player.getInventory().getItemInMainHand())
                : SceneFingerprint.geometry(
                        world.getKey().toString(),
                        best.minX(),
                        best.maxX(),
                        best.minY(),
                        best.maxY(),
                        best.minZ(),
                        best.maxZ(),
                        best.suggestedMaterial() == null ? "air" : best.suggestedMaterial(),
                        best.airCells()
                );
        String confidence = best != null ? best.confidence()
                : (surface != null ? surface.confidence() : "none");
        return new GeometryResult(surface, openings, clearance, palette, fingerprint, confidence, budget);
    }

    private static List<OpeningFacet> findOpenings(
            Player player,
            Block anchor,
            GazeHit gaze,
            String heldMaterial,
            PerceptionBudget budget
    ) {
        List<int[]> directions = orderedDirections(player, gaze.face());
        List<OpeningFacet> found = new ArrayList<>();
        for (Block start : candidateAnchors(player, gaze, anchor, budget)) {
            for (int[] dir : directions) {
                if (budget.truncated() && !found.isEmpty()) {
                    break;
                }
                OpeningFacet opening = scanOpening(start, dir[0], dir[1], heldMaterial, budget);
                if (opening != null) {
                    found.add(opening);
                }
            }
        }
        // Prefer confident, short openings — never the largest distant gap.
        found.sort(Comparator
                .comparingInt((OpeningFacet o) -> confidenceRank(o.confidence())).reversed()
                .thenComparingInt(OpeningFacet::length)
                .thenComparingInt(OpeningFacet::airCells).reversed());
        if (found.size() > 3) {
            return new ArrayList<>(found.subList(0, 3));
        }
        return found;
    }

    private static List<Block> candidateAnchors(
            Player player,
            GazeHit gaze,
            Block primary,
            PerceptionBudget budget
    ) {
        List<Block> anchors = new ArrayList<>();
        if (primary != null && isSolid(primary)) {
            anchors.add(primary);
        }
        World world = player.getWorld();
        int cx = primary != null ? primary.getX() : player.getLocation().getBlockX();
        int cy = primary != null ? primary.getY() : player.getLocation().getBlockY() + 1;
        int cz = primary != null ? primary.getZ() : player.getLocation().getBlockZ();
        // Sample a cross around the hit for exterior corners (cheap, look-aligned).
        double facingX = player.getLocation().getDirection().getX();
        double facingZ = player.getLocation().getDirection().getZ();
        boolean alongX = Math.abs(facingX) >= Math.abs(facingZ);
        for (int lateral = -4; lateral <= 4; lateral++) {
            for (int forward = -1; forward <= 4; forward++) {
                for (int dy = -1; dy <= 3; dy++) {
                    if (!budget.sampleCell()) {
                        return anchors;
                    }
                    int dx = alongX ? forward : lateral;
                    int dz = alongX ? lateral : forward;
                    // Mirror forward both ways along look axis.
                    for (int sign : new int[]{1, -1}) {
                        Block block = world.getBlockAt(
                                cx + dx * (alongX ? sign : 1),
                                cy + dy,
                                cz + dz * (alongX ? 1 : sign)
                        );
                        if (!isSolid(block) || !isOpeningEnd(block)) {
                            continue;
                        }
                        if (anchors.stream().noneMatch(existing -> sameBlock(existing, block))) {
                            anchors.add(block);
                        }
                    }
                }
            }
        }
        if (gaze.hit() && gaze.block() != null && isSolid(gaze.block())
                && anchors.stream().noneMatch(existing -> sameBlock(existing, gaze.block()))) {
            anchors.add(0, gaze.block());
        }
        return anchors;
    }

    private static List<OpeningFacet> preferExteriorOpenings(Player player, List<OpeningFacet> openings) {
        if (openings.size() <= 1) {
            return openings;
        }
        World world = player.getWorld();
        List<OpeningFacet> ranked = new ArrayList<>(openings);
        ranked.sort(Comparator
                .comparingInt((OpeningFacet o) -> exteriorClearance(world, o)).reversed()
                .thenComparingInt(OpeningFacet::length)
                .thenComparingDouble(o -> distanceToOpening(player, o)));
        return ranked;
    }

    private static int exteriorClearance(World world, OpeningFacet opening) {
        int midX = (opening.minX() + opening.maxX()) / 2;
        int midY = opening.minY() + Math.max(0, (opening.height() - 1) / 2);
        int midZ = (opening.minZ() + opening.maxZ()) / 2;
        int airA = 0;
        int airB = 0;
        if ("x".equals(opening.axis())) {
            for (int i = 1; i <= 3; i++) {
                if (!isSolid(world.getBlockAt(midX, midY, midZ + i))) {
                    airA++;
                }
                if (!isSolid(world.getBlockAt(midX, midY, midZ - i))) {
                    airB++;
                }
            }
        } else {
            for (int i = 1; i <= 3; i++) {
                if (!isSolid(world.getBlockAt(midX + i, midY, midZ))) {
                    airA++;
                }
                if (!isSolid(world.getBlockAt(midX - i, midY, midZ))) {
                    airB++;
                }
            }
        }
        // Reward one-sided openness (true exterior face) over through-building gaps.
        return Math.max(airA, airB) * 2 + Math.abs(airA - airB);
    }

    private static double distanceToOpening(Player player, OpeningFacet opening) {
        double px = player.getLocation().getX();
        double pz = player.getLocation().getZ();
        double cx = (opening.minX() + opening.maxX()) / 2.0 + 0.5;
        double cz = (opening.minZ() + opening.maxZ()) / 2.0 + 0.5;
        double dx = px - cx;
        double dz = pz - cz;
        return dx * dx + dz * dz;
    }

    private static boolean sameBlock(Block a, Block b) {
        return a.getX() == b.getX() && a.getY() == b.getY() && a.getZ() == b.getZ();
    }

    private static OpeningFacet scanOpening(
            Block start,
            int stepX,
            int stepZ,
            String heldMaterial,
            PerceptionBudget budget
    ) {
        World world = start.getWorld();
        int scanY = start.getY();
        // Skip contiguous solid run attached to the looked-at corner/edge.
        int distance = 1;
        while (distance <= PerceptionBudget.SCAN_HORIZONTAL) {
            if (!budget.sampleCell()) {
                return null;
            }
            Block block = start.getRelative(stepX * distance, 0, stepZ * distance);
            if (!isSolid(block)) {
                break;
            }
            distance++;
        }
        int airStart = distance;
        boolean sawAir = false;
        Block far = null;
        for (; distance <= PerceptionBudget.SCAN_HORIZONTAL; distance++) {
            if (!budget.sampleCell()) {
                return null;
            }
            Block block = world.getBlockAt(
                    start.getX() + stepX * distance,
                    scanY,
                    start.getZ() + stepZ * distance
            );
            if (!isSolid(block)) {
                sawAir = true;
                continue;
            }
            if (sawAir && distance - airStart >= 1) {
                far = block;
                break;
            }
            return null;
        }
        if (far == null) {
            return null;
        }
        // Openings are between matching posts/edges. Fill material may differ (held/prompt).
        if (start.getType() != far.getType()) {
            return null;
        }
        // Reject mid-wall cross-sections (U-building interiors); allow posts + exterior corners.
        if (!isOpeningEnd(start) || !isOpeningEnd(far)) {
            return null;
        }

        int downStart = measureDown(start, budget);
        int downFar = measureDown(far, budget);
        int upStart = measureUp(start, budget);
        int upFar = measureUp(far, budget);
        int minY = Math.min(start.getY() - downStart, far.getY() - downFar);
        int maxY = Math.max(start.getY() + upStart, far.getY() + upFar);
        int height = Math.max(2, Math.min(PerceptionBudget.SCAN_VERTICAL, maxY - minY + 1));

        boolean alongX = stepZ == 0;
        int minX = Math.min(start.getX(), far.getX());
        int maxX = Math.max(start.getX(), far.getX());
        int minZ = Math.min(start.getZ(), far.getZ());
        int maxZ = Math.max(start.getZ(), far.getZ());
        int length = alongX ? (maxX - minX + 1) : (maxZ - minZ + 1);
        if (length < 2 || length > PerceptionBudget.MAX_OPENING_LENGTH) {
            return null;
        }
        // Cheap air estimate from base + mid rows only (avoids budget abort on tall faces).
        int airBase = countAirAlong(world, alongX, minX, maxX, minY, minZ, maxZ, budget);
        int midY = minY + Math.max(0, (height - 1) / 2);
        int airMid = countAirAlong(world, alongX, minX, maxX, midY, minZ, maxZ, budget);
        int rowSpan = length;
        if (airBase == 0 && airMid == 0) {
            return null;
        }
        int airCells = Math.max(1, (airBase + airMid) * Math.max(1, height / 2));
        int spanCells = Math.max(1, rowSpan * height);
        // Mostly-solid spans are walls, not openings.
        if (airBase * 100 / rowSpan < 35 && airMid * 100 / rowSpan < 35) {
            return null;
        }
        // Matching posts with a clear gap are usable even if the tick budget was tight.
        String confidence = (airCells >= 8 && length >= 3 && height >= 3) ? "high" : "medium";
        String suggested = heldMaterial != null ? heldMaterial
                : materialKey(start.getType());
        return new OpeningFacet(
                alongX ? "x" : "z",
                minX,
                maxX,
                minY,
                minY + height - 1,
                minZ,
                maxZ,
                length,
                height,
                airCells,
                materialKey(start.getType()),
                materialKey(far.getType()),
                suggested,
                confidence
        );
    }

    private static int countAirAlong(
            World world,
            boolean alongX,
            int minX,
            int maxX,
            int y,
            int minZ,
            int maxZ,
            PerceptionBudget budget
    ) {
        int air = 0;
        if (alongX) {
            for (int x = minX; x <= maxX; x++) {
                budget.sampleCell();
                if (!isSolid(world.getBlockAt(x, y, minZ))) {
                    air++;
                }
            }
        } else {
            for (int z = minZ; z <= maxZ; z++) {
                budget.sampleCell();
                if (!isSolid(world.getBlockAt(minX, y, z))) {
                    air++;
                }
            }
        }
        return air;
    }

    private static int measureUp(Block edge, PerceptionBudget budget) {
        int up = 0;
        World world = edge.getWorld();
        for (int y = edge.getY() + 1; y <= edge.getY() + PerceptionBudget.SCAN_VERTICAL; y++) {
            if (!budget.sampleCell()) {
                break;
            }
            if (!isSolid(world.getBlockAt(edge.getX(), y, edge.getZ()))) {
                break;
            }
            up++;
        }
        return up;
    }

    private static int measureDown(Block edge, PerceptionBudget budget) {
        int down = 0;
        World world = edge.getWorld();
        for (int y = edge.getY() - 1; y >= edge.getY() - PerceptionBudget.SCAN_VERTICAL; y--) {
            if (!budget.sampleCell()) {
                break;
            }
            if (!isSolid(world.getBlockAt(edge.getX(), y, edge.getZ()))) {
                break;
            }
            down++;
        }
        return down;
    }

    private static SurfaceFacet surfaceFromGaze(GazeHit gaze, List<OpeningFacet> openings) {
        if (!gaze.hit() || gaze.block() == null || gaze.face() == null) {
            return null;
        }
        if (!openings.isEmpty()) {
            OpeningFacet opening = openings.get(0);
            return new SurfaceFacet(
                    opening.axis(),
                    gaze.face().name().toLowerCase(Locale.ROOT),
                    opening.minX(),
                    opening.maxX(),
                    opening.minY(),
                    opening.maxY(),
                    opening.minZ(),
                    opening.maxZ(),
                    opening.length(),
                    opening.height(),
                    materialKey(gaze.block().getType()),
                    opening.confidence()
            );
        }
        Block block = gaze.block();
        return new SurfaceFacet(
                "y",
                gaze.face().name().toLowerCase(Locale.ROOT),
                block.getX(),
                block.getX(),
                block.getY(),
                block.getY(),
                block.getZ(),
                block.getZ(),
                1,
                1,
                materialKey(block.getType()),
                "medium"
        );
    }

    private static ClearanceFacet clearanceAhead(Player player, GazeHit gaze, PerceptionBudget budget) {
        BlockFace forward = yawToFace(player.getLocation().getYaw());
        Block origin = gaze.hit() && gaze.block() != null
                ? gaze.block().getRelative(gaze.face() == null ? forward : gaze.face())
                : player.getLocation().getBlock().getRelative(forward, 2);
        int width = 7;
        int height = 7;
        int depth = 7;
        int minX = origin.getX() - width / 2;
        int maxX = origin.getX() + width / 2;
        int minY = origin.getY();
        int maxY = origin.getY() + height - 1;
        int minZ = origin.getZ() - depth / 2;
        int maxZ = origin.getZ() + depth / 2;
        int air = 0;
        World world = player.getWorld();
        for (int x = minX; x <= maxX; x++) {
            for (int y = minY; y <= maxY; y++) {
                for (int z = minZ; z <= maxZ; z++) {
                    if (!budget.sampleCell()) {
                        break;
                    }
                    if (!isSolid(world.getBlockAt(x, y, z))) {
                        air++;
                    }
                }
            }
        }
        int volume = width * height * depth;
        String confidence = air >= volume * 0.7 ? "high" : (air >= volume * 0.4 ? "medium" : "low");
        return new ClearanceFacet(minX, maxX, minY, maxY, minZ, maxZ, width, height, depth, air, confidence);
    }

    private static List<PaletteEntry> samplePalette(World world, Block anchor, PerceptionBudget budget) {
        java.util.Map<String, Integer> counts = new java.util.HashMap<>();
        int r = Math.min(8, PerceptionBudget.PALETTE_RADIUS);
        for (int x = -r; x <= r; x++) {
            for (int y = -2; y <= 6; y++) {
                for (int z = -r; z <= r; z++) {
                    if (!budget.sampleCell()) {
                        break;
                    }
                    Block block = world.getBlockAt(anchor.getX() + x, anchor.getY() + y, anchor.getZ() + z);
                    if (!isSolid(block)) {
                        continue;
                    }
                    String key = materialKey(block.getType());
                    counts.merge(key, 1, Integer::sum);
                }
            }
        }
        return counts.entrySet().stream()
                .sorted((a, b) -> Integer.compare(b.getValue(), a.getValue()))
                .limit(8)
                .map(entry -> new PaletteEntry(entry.getKey(), entry.getValue()))
                .toList();
    }

    /**
     * Prefer the player's horizontal look axis so open-face scans walk along the
     * gap (e.g. east along a missing south wall) instead of into the solid wall plane.
     */
    private static List<int[]> orderedDirections(Player player, BlockFace face) {
        List<int[]> directions = new ArrayList<>(4);
        double facingX = player.getLocation().getDirection().getX();
        double facingZ = player.getLocation().getDirection().getZ();
        if (Math.abs(facingX) >= Math.abs(facingZ)) {
            directions.add(new int[]{facingX >= 0 ? 1 : -1, 0});
            directions.add(new int[]{facingX >= 0 ? -1 : 1, 0});
            directions.add(new int[]{0, facingZ >= 0 ? 1 : -1});
            directions.add(new int[]{0, facingZ >= 0 ? -1 : 1});
        } else {
            directions.add(new int[]{0, facingZ >= 0 ? 1 : -1});
            directions.add(new int[]{0, facingZ >= 0 ? -1 : 1});
            directions.add(new int[]{facingX >= 0 ? 1 : -1, 0});
            directions.add(new int[]{facingX >= 0 ? -1 : 1, 0});
        }
        // Keep face-aligned axes as low-priority fallbacks when look is ambiguous.
        if (face == BlockFace.EAST || face == BlockFace.WEST) {
            addUnique(directions, 0, 1);
            addUnique(directions, 0, -1);
        } else if (face == BlockFace.NORTH || face == BlockFace.SOUTH) {
            addUnique(directions, 1, 0);
            addUnique(directions, -1, 0);
        }
        return directions;
    }

    private static void addUnique(List<int[]> directions, int stepX, int stepZ) {
        for (int[] existing : directions) {
            if (existing[0] == stepX && existing[1] == stepZ) {
                return;
            }
        }
        directions.add(new int[]{stepX, stepZ});
    }

    private static Block resolveAnchor(Player player, GazeHit gaze, PerceptionBudget budget) {
        if (gaze.hit() && gaze.block() != null && isSolid(gaze.block())) {
            return gaze.block();
        }
        // Creative float / miss: walk the look ray for the first solid post/edge.
        var direction = player.getLocation().getDirection().clone().setY(0);
        if (direction.lengthSquared() < 1.0e-6) {
            direction = player.getLocation().getDirection().clone();
        }
        direction.normalize();
        int startX = player.getLocation().getBlockX();
        int startY = Math.max(player.getLocation().getBlockY(), gaze.hit() && gaze.block() != null
                ? gaze.block().getY()
                : player.getLocation().getBlockY());
        int startZ = player.getLocation().getBlockZ();
        World world = player.getWorld();
        for (int distance = 1; distance <= 8; distance++) {
            if (!budget.sampleCell()) {
                break;
            }
            int x = startX + (int) Math.round(direction.getX() * distance);
            int z = startZ + (int) Math.round(direction.getZ() * distance);
            for (int dy = 0; dy <= 2; dy++) {
                Block block = world.getBlockAt(x, startY + dy, z);
                if (isSolid(block)) {
                    return block;
                }
            }
        }
        return gaze.hit() && gaze.block() != null ? gaze.block() : player.getLocation().getBlock();
    }

    private static BlockFace yawToFace(float yaw) {
        float value = yaw % 360f;
        if (value < 0f) {
            value += 360f;
        }
        if (value >= 45 && value < 135) {
            return BlockFace.WEST;
        }
        if (value >= 135 && value < 225) {
            return BlockFace.NORTH;
        }
        if (value >= 225 && value < 315) {
            return BlockFace.EAST;
        }
        return BlockFace.SOUTH;
    }

    private static boolean isSolid(Block block) {
        Material type = block.getType();
        return !type.isAir() && type.isSolid();
    }

    /** Freestanding posts (0) or exterior corners (1); rejects mid-wall edges (2+). */
    private static boolean isOpeningEnd(Block block) {
        int solid = 0;
        if (isSolid(block.getRelative(1, 0, 0))) {
            solid++;
        }
        if (isSolid(block.getRelative(-1, 0, 0))) {
            solid++;
        }
        if (isSolid(block.getRelative(0, 0, 1))) {
            solid++;
        }
        if (isSolid(block.getRelative(0, 0, -1))) {
            solid++;
        }
        return solid <= 1;
    }

    private static String materialKey(Material material) {
        return material.getKey().getKey();
    }

    private static int confidenceRank(String confidence) {
        return switch (confidence) {
            case "high" -> 3;
            case "medium" -> 2;
            case "low" -> 1;
            default -> 0;
        };
    }
}
