package com.neighborhood.agent;

/**
 * Pure span math for parametric bridges/roads/paths across water or land.
 *
 * <p>World sampling lives in {@link PlaceShapeExecutor}; this class only
 * resolves start/end indices, deck Y, and walkable terrain profiles.
 */
final class BridgeSpan {
    /** Centerline steps per FAWE chunk / gaze span (width multiplies cell budget). */
    static final int MAX_LENGTH = 1024;
    static final int DEFAULT_BRIDGE_LENGTH = 24;
    static final int DEFAULT_PATH_LENGTH = 48;
    /** Prefer gold short-bridge schem only when gap is this short or less. */
    static final int TINY_GAP_TEMPLATE_MAX = 12;
    /** Max |ΔY| per step so trails stay walkable (MC step-up is 1). */
    static final int MAX_STEP = 1;

    enum Kind {
        LAND,
        WATER,
        GAP,
        LAVA
    }

    record Column(Kind kind, int surfaceY, int solidTopY) {
        static Column land(int solidTopY) {
            return new Column(Kind.LAND, solidTopY, solidTopY);
        }

        static Column water(int surfaceY, int solidTopY) {
            return new Column(Kind.WATER, surfaceY, solidTopY);
        }

        static Column gap(int surfaceY) {
            return new Column(Kind.GAP, surfaceY, surfaceY - 8);
        }

        static Column lava(int surfaceY) {
            return new Column(Kind.LAVA, surfaceY, surfaceY - 1);
        }

        boolean isCrossing() {
            return kind == Kind.WATER || kind == Kind.GAP || kind == Kind.LAVA;
        }
    }

    /**
     * @param columns samples at distance 1..N in look direction (index 0 = 1 block ahead)
     * @param explicitLength optional length override; null means auto-span
     */
    record Result(
            int startDist,
            int endDist,
            int deckY,
            boolean crossedGap,
            boolean foundFarShore
    ) {
        int length() {
            return endDist - startDist + 1;
        }

        boolean tinyGapFitsTemplate() {
            return crossedGap && length() <= TINY_GAP_TEMPLATE_MAX;
        }
    }

    private BridgeSpan() {
    }

    /**
     * Resolve a bridge deck across water/gap. Returns null when no far shore
     * is visible and the player did not give an explicit length.
     */
    static Result resolveBridge(Column[] columns, Integer explicitLength, int fallbackDeckY) {
        Result result = resolve(columns, explicitLength, fallbackDeckY, true);
        if (result == null) {
            return null;
        }
        if (result.crossedGap() && !result.foundFarShore() && explicitLength == null) {
            return null;
        }
        return result;
    }

    /** Land path/road: forward run with optional water segments. */
    static Result resolvePath(Column[] columns, Integer explicitLength, int fallbackDeckY) {
        Result result = resolve(columns, explicitLength, fallbackDeckY, false);
        if (result != null) {
            return result;
        }
        // Path with only open water ahead and no length → still fail closed.
        return null;
    }

    /**
     * Walkable Y profile along a span. Clamps step changes to ±{@link #MAX_STEP}
     * so hills become gentle terraces instead of cliff cuts.
     */
    static int[] walkableProfile(Column[] columns, int startDist, int endDist, int seedY) {
        int len = endDist - startDist + 1;
        int[] ys = new int[len];
        int prev = seedY;
        for (int i = 0; i < len; i++) {
            Column col = columns[startDist - 1 + i];
            int target = col.surfaceY;
            int next;
            if (target > prev + MAX_STEP) {
                next = prev + MAX_STEP;
            } else if (target < prev - MAX_STEP) {
                next = prev - MAX_STEP;
            } else {
                next = target;
            }
            ys[i] = next;
            prev = next;
        }
        return ys;
    }

    /** Minimum inclusive centerline length for a ±1 stair between two heights. */
    static int minStairsLength(int startY, int endY) {
        return Math.abs(endY - startY) + 1;
    }

    /**
     * Y for each centerline index with only single-block steps, ending at
     * {@code endY} whenever length allows.
     */
    static int[] stairProfile(int len, int startY, int endY) {
        int[] ys = new int[Math.max(1, len)];
        ys[0] = startY;
        if (len <= 1) {
            return ys;
        }
        for (int i = 1; i < len; i++) {
            int rem = len - 1 - i;
            int prev = ys[i - 1];
            int ideal = startY + (int) Math.round((endY - startY) * (i / (double) (len - 1)));
            int next = ideal;
            if (next > prev + MAX_STEP) {
                next = prev + MAX_STEP;
            } else if (next < prev - MAX_STEP) {
                next = prev - MAX_STEP;
            }
            // Keep endY reachable with the remaining ±1 steps.
            if (endY - next > rem) {
                next = prev + MAX_STEP;
            } else if (next - endY > rem) {
                next = prev - MAX_STEP;
            }
            ys[i] = next;
        }
        ys[len - 1] = endY;
        // Re-walk backward if forcing the end created a >1 jump.
        for (int i = len - 1; i > 0; i--) {
            int diff = ys[i] - ys[i - 1];
            if (diff > MAX_STEP) {
                ys[i - 1] = ys[i] - MAX_STEP;
            } else if (diff < -MAX_STEP) {
                ys[i - 1] = ys[i] + MAX_STEP;
            }
        }
        ys[0] = startY;
        for (int i = 1; i < len; i++) {
            int diff = ys[i] - ys[i - 1];
            if (diff > MAX_STEP) {
                ys[i] = ys[i - 1] + MAX_STEP;
            } else if (diff < -MAX_STEP) {
                ys[i] = ys[i - 1] - MAX_STEP;
            }
        }
        return ys;
    }

    /**
     * Blend a stair ramp with terrain on land columns (still ±1 from previous).
     * Water/gap columns keep the ramp so decks step cleanly to shores.
     */
    static int[] stairProfileBlended(Column[] columns, int startY, int endY, boolean followTerrain) {
        int[] ys = stairProfile(columns.length, startY, endY);
        if (!followTerrain || columns.length == 0) {
            return ys;
        }
        ys[0] = startY;
        for (int i = 1; i < columns.length; i++) {
            int prev = ys[i - 1];
            int ramp = ys[i];
            Column col = columns[i];
            int target = ramp;
            if (!col.isCrossing()) {
                int terrain = col.surfaceY;
                if (Math.abs(terrain - ramp) <= 2) {
                    target = terrain;
                }
            } else {
                // Keep deck at least at the water/gap surface.
                target = Math.max(ramp, col.surfaceY);
            }
            if (target > prev + MAX_STEP) {
                target = prev + MAX_STEP;
            } else if (target < prev - MAX_STEP) {
                target = prev - MAX_STEP;
            }
            ys[i] = target;
        }
        // Nudge toward endY with remaining room on the last few steps.
        ys[columns.length - 1] = clampStep(ys[Math.max(0, columns.length - 2)], endY);
        return ys;
    }

    /**
     * Stairs that follow outdoor grade, then apply a short ±1 suffix ramp to
     * {@code endY}.
     *
     * <p>Previously, endY reachability was applied on every forward step and a
     * full-run backward repair pulled the whole approach underground whenever
     * the sill was below grade. This version follows terrain first, then only
     * rewrites a terminal suffix of length {@code |endY - grade|}.
     *
     * @param terrainY per-centerline solid surface Y (same length as the run)
     */
    static int[] stairProfileGroundHug(int[] terrainY, int startY, int endY) {
        int len = terrainY == null ? 0 : terrainY.length;
        int[] ys = new int[Math.max(1, len)];
        if (len == 0) {
            ys[0] = startY;
            return ys;
        }
        if (len == 1) {
            ys[0] = endY;
            return ys;
        }

        // Phase 1: follow terrain (±1). Do not bias toward endY yet.
        ys[0] = startY;
        for (int i = 1; i < len; i++) {
            ys[i] = clampStep(ys[i - 1], terrainY[i]);
        }

        // Phase 2: terminal ramp only — leave the approach on grade.
        int gradeAtDoor = ys[len - 1];
        int rampLen = Math.abs(endY - gradeAtDoor);
        int rampStart = Math.max(1, len - rampLen);
        // rampStart is the first index that may leave grade toward endY.
        // Keep [0, rampStart) from phase 1; rebuild [rampStart, len).
        for (int i = rampStart; i < len; i++) {
            int prev = ys[i - 1];
            int rem = len - 1 - i;
            int target = endY;
            if (endY - prev > rem + MAX_STEP) {
                target = prev + MAX_STEP;
            } else if (prev - endY > rem + MAX_STEP) {
                target = prev - MAX_STEP;
            } else {
                target = clampStep(prev, endY);
                // Prefer staying on grade until the last moments of the suffix.
                int grade = terrainY[i];
                if (Math.abs(grade - endY) <= rem
                        && Math.abs(grade - prev) <= MAX_STEP) {
                    target = grade;
                }
                if (Math.abs(target - endY) > rem) {
                    target = endY > prev ? prev + MAX_STEP : prev - MAX_STEP;
                }
            }
            ys[i] = clampStep(prev, target);
        }
        ys[len - 1] = endY;
        if (Math.abs(ys[len - 1] - ys[len - 2]) > MAX_STEP) {
            ys[len - 1] = clampStep(ys[len - 2], endY);
        }

        // Hard floor on the approach: never sit under sampled ground before
        // the ramp (prevents headroom clears from carving a trench).
        for (int i = 0; i < rampStart; i++) {
            if (ys[i] < terrainY[i]) {
                int prev = i == 0 ? startY : ys[i - 1];
                ys[i] = clampStep(prev, terrainY[i]);
                if (ys[i] < terrainY[i]) {
                    ys[i] = Math.min(terrainY[i], prev + MAX_STEP);
                }
            }
        }
        // Re-seal ±1 after approach floor snaps.
        for (int i = 1; i < len; i++) {
            ys[i] = clampStep(ys[i - 1], ys[i]);
        }
        if (Math.abs(endY - ys[len - 2]) <= MAX_STEP) {
            ys[len - 1] = endY;
        }
        return ys;
    }

    /** First index of the terminal door ramp for a ground-hug profile. */
    static int groundHugRampStart(int[] terrainY, int startY, int endY) {
        if (terrainY == null || terrainY.length <= 1) {
            return 0;
        }
        int[] probe = new int[terrainY.length];
        probe[0] = startY;
        for (int i = 1; i < terrainY.length; i++) {
            probe[i] = clampStep(probe[i - 1], terrainY[i]);
        }
        int rampLen = Math.abs(endY - probe[probe.length - 1]);
        return Math.max(1, terrainY.length - rampLen);
    }

    private static int clampStep(int prev, int target) {
        if (target > prev + MAX_STEP) {
            return prev + MAX_STEP;
        }
        if (target < prev - MAX_STEP) {
            return prev - MAX_STEP;
        }
        return target;
    }

    /**
     * Pick a walk Y near the player's feet band. Never returns a lakebed under
     * water — that is the pier "start one block too deep" failure mode.
     *
     * @param nearY    feet / seed band (player block Y or known deck)
     * @param solidTop solid found by a column scan (may be underwater)
     * @param waterTop top water block, or {@code null} if none
     * @param maxDrop  how far below {@code nearY} a solid may sit and still count
     */
    static int preferWalkSurface(int nearY, int solidTop, Integer waterTop, int maxDrop) {
        int minWalk = nearY - Math.max(0, maxDrop);
        boolean solidUnderWater = waterTop != null && solidTop < waterTop;
        if (solidUnderWater) {
            // Lakebed under a water column — keep the deck at waterline / feet.
            return Math.max(waterTop, nearY - 1);
        }
        if (solidTop < minWalk) {
            // Deep solid with no water (cave / ravine) — stay at feet deck.
            return Math.max(minWalk, nearY - 1);
        }
        return solidTop;
    }

    /**
     * Trail Y between marker anchors: follow the ±1 ramp but never dig under
     * sampled outdoor grade (path-marker trench + floating grass lids).
     */
    static int trailFollowY(int rampY, int terrainY, boolean crossing, int deckFloor) {
        if (crossing) {
            return Math.max(rampY, Math.max(terrainY, deckFloor));
        }
        return Math.max(rampY, terrainY);
    }

    /** Inclusive length of a marker leg after extending for stair room. */
    static int lineLengthWithStairRoom(int x0, int z0, int x1, int z1, int startY, int endY) {
        int[] end = extendedEnd(x0, z0, x1, z1, startY, endY);
        return lineLengthXZ(x0, z0, end[0], end[1]);
    }

    /**
     * Push the far end forward when |ΔY| needs more horizontal steps than the
     * straight line provides (so stairs can rise/fall one block at a time).
     */
    static int[] extendedEnd(int x0, int z0, int x1, int z1, int startY, int endY) {
        int need = minStairsLength(startY, endY);
        int have = lineLengthXZ(x0, z0, x1, z1);
        if (have >= need) {
            return new int[]{x1, z1};
        }
        int extra = need - have;
        int dx = Integer.signum(x1 - x0);
        int dz = Integer.signum(z1 - z0);
        if (dx == 0 && dz == 0) {
            dx = 1;
        }
        // Prefer the dominant axis so width stays meaningful.
        if (Math.abs(x1 - x0) >= Math.abs(z1 - z0)) {
            if (dx == 0) {
                dx = 1;
            }
            dz = 0;
        } else {
            if (dz == 0) {
                dz = 1;
            }
            dx = 0;
        }
        return new int[]{x1 + dx * extra, z1 + dz * extra};
    }

    private static Result resolve(
            Column[] columns,
            Integer explicitLength,
            int fallbackDeckY,
            boolean bridgeMode
    ) {
        if (columns == null || columns.length == 0) {
            int def = bridgeMode ? DEFAULT_BRIDGE_LENGTH : DEFAULT_PATH_LENGTH;
            int len = clampLen(explicitLength != null ? explicitLength : def);
            return new Result(1, len, fallbackDeckY, false, true);
        }
        int n = columns.length;
        int crossStart = -1;
        for (int i = 0; i < n; i++) {
            if (columns[i].isCrossing()) {
                crossStart = i;
                break;
            }
        }

        if (crossStart >= 0 && (bridgeMode || crossStart <= 2)) {
            int crossEnd = crossStart;
            int landEnd = -1;
            for (int i = crossStart; i < n; i++) {
                if (columns[i].isCrossing()) {
                    crossEnd = i;
                } else if (columns[i].kind == Kind.LAND) {
                    landEnd = i;
                    break;
                } else {
                    break;
                }
            }
            int deckY = deckYForCrossing(columns, crossStart, crossEnd, fallbackDeckY);
            int startIdx = crossStart;
            if (crossStart > 0 && shoreNearDeck(columns[crossStart - 1], deckY)) {
                startIdx = crossStart - 1;
            }
            boolean foundShore = landEnd >= 0 && shoreNearDeck(columns[landEnd], deckY);
            int endIdx = foundShore ? landEnd : crossEnd;
            int startDist = distOf(startIdx);
            int endDist = distOf(endIdx);
            if (explicitLength != null) {
                endDist = Math.min(n, startDist + clampLen(explicitLength) - 1);
                return new Result(startDist, endDist, deckY, true, foundShore);
            }
            if (!foundShore) {
                if (bridgeMode) {
                    return null;
                }
                // Path into water with no far shore: stop at water's edge.
                endDist = distOf(Math.max(0, crossStart - 1));
                if (endDist < 1) {
                    return null;
                }
                return new Result(1, endDist, fallbackDeckY, false, false);
            }
            return new Result(startDist, endDist, deckY, true, true);
        }

        // Land corridor ahead (path/road), or bridge with no water (short deck).
        int def = bridgeMode ? DEFAULT_BRIDGE_LENGTH : DEFAULT_PATH_LENGTH;
        int len = clampLen(explicitLength != null ? explicitLength : def);
        len = Math.min(len, n);
        int deckY = fallbackDeckY;
        for (int i = 0; i < len; i++) {
            if (columns[i].kind == Kind.LAND) {
                deckY = columns[i].surfaceY;
                break;
            }
        }
        return new Result(1, len, deckY, false, true);
    }

    private static int distOf(int index) {
        return index + 1;
    }

    private static int deckYForCrossing(
            Column[] columns, int crossStart, int crossEnd, int fallbackDeckY
    ) {
        int sum = 0;
        int count = 0;
        for (int i = crossStart; i <= crossEnd && i < columns.length; i++) {
            if (columns[i].kind == Kind.WATER || columns[i].kind == Kind.GAP) {
                sum += columns[i].surfaceY;
                count++;
            }
        }
        if (count > 0) {
            return sum / count;
        }
        return fallbackDeckY;
    }

    private static boolean shoreNearDeck(Column col, int deckY) {
        return col.kind == Kind.LAND && Math.abs(col.surfaceY - deckY) <= 4;
    }

    private static int clampLen(int length) {
        return Math.max(2, Math.min(MAX_LENGTH, length));
    }

    /** Bresenham line on the XZ plane (inclusive endpoints), uncapped. */
    static int[][] lineXZ(int x0, int z0, int x1, int z1) {
        int len = lineLengthXZ(x0, z0, x1, z1);
        int[][] out = new int[len][2];
        LineCursor cursor = LineCursor.start(x0, z0, x1, z1);
        int n = 0;
        while (cursor.hasNext()) {
            out[n][0] = cursor.x();
            out[n][1] = cursor.z();
            n++;
            cursor.step();
        }
        return out;
    }

    /** Inclusive Bresenham step count (no allocation). */
    static int lineLengthXZ(int x0, int z0, int x1, int z1) {
        int n = 0;
        LineCursor cursor = LineCursor.start(x0, z0, x1, z1);
        while (cursor.hasNext()) {
            n++;
            cursor.step();
        }
        return n;
    }

    /**
     * Streaming Bresenham cursor — pull {@link #nextChunk(int)} without
     * materializing the full polyline into memory.
     */
    static final class LineCursor {
        private int x;
        private int z;
        private final int x1;
        private final int z1;
        private final int dx;
        private final int dz;
        private final int sx;
        private final int sz;
        private int err;
        private boolean hasNext;

        private LineCursor(int x0, int z0, int x1, int z1) {
            this.x = x0;
            this.z = z0;
            this.x1 = x1;
            this.z1 = z1;
            this.dx = Math.abs(x1 - x0);
            this.dz = Math.abs(z1 - z0);
            this.sx = x0 < x1 ? 1 : -1;
            this.sz = z0 < z1 ? 1 : -1;
            this.err = this.dx - this.dz;
            this.hasNext = true;
        }

        static LineCursor start(int x0, int z0, int x1, int z1) {
            return new LineCursor(x0, z0, x1, z1);
        }

        int x() {
            return x;
        }

        int z() {
            return z;
        }

        boolean hasNext() {
            return hasNext;
        }

        /** Consume current point and advance (or finish after the endpoint). */
        void step() {
            if (!hasNext) {
                return;
            }
            if (x == x1 && z == z1) {
                hasNext = false;
                return;
            }
            int e2 = 2 * err;
            if (e2 > -dz) {
                err -= dz;
                x += sx;
            }
            if (e2 < dx) {
                err += dx;
                z += sz;
            }
        }

        /** Next up-to-{@code maxPoints} inclusive samples. Empty when finished. */
        int[][] nextChunk(int maxPoints) {
            if (!hasNext || maxPoints < 1) {
                return new int[0][2];
            }
            int[][] buf = new int[maxPoints][2];
            int n = 0;
            while (n < maxPoints && hasNext) {
                buf[n][0] = x;
                buf[n][1] = z;
                n++;
                step();
            }
            if (n == maxPoints) {
                return buf;
            }
            int[][] out = new int[n][2];
            System.arraycopy(buf, 0, out, 0, n);
            return out;
        }
    }
}
