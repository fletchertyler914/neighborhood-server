package com.neighborhood.agent;

/**
 * Pure paste-origin math for curated schematics.
 *
 * <p>WorldEdit pastes so clipboard origin lands at {@code targetOrigin}. Relative
 * footprint bounds are {@code regionMin/Max - clipboardOrigin}.
 *
 * <p>Policy: place where the player is looking (gaze) when safe; else facing
 * offset near them. Never search distant wilderness. Refuse player overlap.
 */
final class SchematicPlacement {
    /** Extra blocks beyond half-footprint so the player stands clearly outside. */
    static final int PLAYER_MARGIN = 2;

    /**
     * Footprints at or above this horizontal extent are "mega" (cathedral /
     * mansion class) for sampling / messaging — not for skipping gaze.
     */
    static final int MEGA_EXTENT = 40;

    /**
     * Gaze hits farther than half-extent + this slack fall back to facing so
     * we don't center a build on a far skyline hit.
     */
    static final int GAZE_SLACK = 8;

    /** Gaze/facing could not find a clear paste origin. */
    static final String UNSAFE_MESSAGE =
            "I can't build there — step back a bit and try again.";

    /** Footprint would cover the requesting player. */
    static final String OVERLAP_MESSAGE =
            "You're in the way — step aside and try again.";

    /**
     * Paste would wipe/flatten ground — ask before clearing (companion pending).
     */
    static final String CLEAR_ASK_MESSAGE =
            "I'll need to clear some ground there first — want me to? Try: yes";

    private SchematicPlacement() {
    }

    record Footprint(int minX, int minY, int minZ, int maxX, int maxY, int maxZ) {
        int width() {
            return maxX - minX + 1;
        }

        int depth() {
            return maxZ - minZ + 1;
        }

        int height() {
            return maxY - minY + 1;
        }

        int centerX() {
            return Math.floorDiv(minX + maxX, 2);
        }

        int centerZ() {
            return Math.floorDiv(minZ + maxZ, 2);
        }

        int maxHorizontalExtent() {
            return Math.max(width(), depth());
        }

        boolean isMega() {
            return maxHorizontalExtent() >= MEGA_EXTENT;
        }

        boolean valid() {
            return width() >= 1 && depth() >= 1 && height() >= 1;
        }
    }

    /**
     * Pick a paste origin: safe gaze first (where they're looking), else
     * facing-offset. Optional {@code forwardBlocks} overrides facing clearance
     * when the player said e.g. "20 blocks in front".
     */
    static int[] resolveOrigin(
            int playerX,
            int playerY,
            int playerZ,
            double dirX,
            double dirZ,
            Footprint fp,
            Integer hitX,
            Integer hitY,
            Integer hitZ,
            String face,
            Integer supportX,
            Integer supportY,
            Integer supportZ,
            Integer forwardBlocks
    ) {
        if (!fp.valid()) {
            return null;
        }
        if (hitX != null && hitY != null && hitZ != null && face != null
                && supportX != null && supportY != null && supportZ != null
                && gazeHitIsNearEnough(playerX, playerZ, hitX, hitZ, fp)) {
            int[] gaze = gazeAwareOrigin(
                    hitX, hitY, hitZ, face,
                    supportX, supportY, supportZ,
                    playerX, playerY, playerZ,
                    fp
            );
            if (gaze != null) {
                return gaze;
            }
        }
        int[] facing = facingOffsetOrigin(
                playerX, playerY, playerZ, dirX, dirZ, fp, forwardBlocks
        );
        if (facing != null && !footprintOverlapsPlayer(facing, fp, playerX, playerY, playerZ)) {
            return facing;
        }
        return null;
    }

    /** Back-compat overload without forward override. */
    static int[] resolveOrigin(
            int playerX,
            int playerY,
            int playerZ,
            double dirX,
            double dirZ,
            Footprint fp,
            Integer hitX,
            Integer hitY,
            Integer hitZ,
            String face,
            Integer supportX,
            Integer supportY,
            Integer supportZ
    ) {
        return resolveOrigin(
                playerX, playerY, playerZ, dirX, dirZ, fp,
                hitX, hitY, hitZ, face, supportX, supportY, supportZ, null
        );
    }

    /**
     * Accept gaze when the hit is within half-extent + slack of the player
     * (gaze ray is already capped ~48). Reject under/beside separately.
     */
    static boolean gazeHitIsNearEnough(
            int playerX,
            int playerZ,
            int hitX,
            int hitZ,
            Footprint fp
    ) {
        int chebyshev = Math.max(Math.abs(hitX - playerX), Math.abs(hitZ - playerZ));
        int maxGaze = halfExtentClearance(fp, fp.width() >= fp.depth()) + GAZE_SLACK;
        return chebyshev <= maxGaze;
    }

    /**
     * Near footprint edge is half-extent + {@link #PLAYER_MARGIN} in front of
     * the player (or an explicit forward distance). Returns null if overlap.
     */
    static int[] facingOffsetOrigin(
            int playerX,
            int playerY,
            int playerZ,
            double dirX,
            double dirZ,
            Footprint fp,
            Integer forwardBlocks
    ) {
        boolean alongX = Math.abs(dirX) > Math.abs(dirZ);
        int clearance = forwardBlocks != null && forwardBlocks > 0
                ? forwardBlocks
                : halfExtentClearance(fp, alongX);
        int targetX;
        int targetZ;
        if (alongX) {
            targetX = dirX >= 0
                    ? playerX + clearance - fp.minX()
                    : playerX - clearance - fp.maxX();
            targetZ = playerZ - fp.centerZ();
        } else {
            targetX = playerX - fp.centerX();
            targetZ = dirZ >= 0
                    ? playerZ + clearance - fp.minZ()
                    : playerZ - clearance - fp.maxZ();
        }
        // Floor at feet Y so the schem sits ON the block the player stands on
        // (same as UP-face: hitY+1). playerY-1 sank builds one block into the pad.
        int targetY = playerY - fp.minY();
        int[] origin = {targetX, targetY, targetZ};
        if (footprintOverlapsPlayer(origin, fp, playerX, playerY, playerZ)) {
            return null;
        }
        return origin;
    }

    static int[] facingOffsetOrigin(
            int playerX,
            int playerY,
            int playerZ,
            double dirX,
            double dirZ,
            Footprint fp
    ) {
        return facingOffsetOrigin(playerX, playerY, playerZ, dirX, dirZ, fp, null);
    }

    /** Half footprint along the facing axis, plus margin. */
    static int halfExtentClearance(Footprint fp, boolean alongX) {
        int extent = alongX ? fp.width() : fp.depth();
        return (extent / 2) + PLAYER_MARGIN;
    }

    /**
     * Gaze-relative origin. Null when the hit is under/beside the player,
     * or the footprint would overlap their column.
     */
    static int[] gazeAwareOrigin(
            int hitX,
            int hitY,
            int hitZ,
            String face,
            int supportX,
            int supportY,
            int supportZ,
            int playerX,
            int playerY,
            int playerZ,
            Footprint fp
    ) {
        if (!fp.valid()) {
            return null;
        }
        if (isUnderOrBesidePlayer(hitX, hitZ, playerX, playerZ)) {
            return null;
        }

        int targetX = supportX - fp.centerX();
        int targetZ = supportZ - fp.centerZ();
        int targetY = supportY - fp.minY();

        switch (face) {
            case "UP" -> {
                targetY = hitY + 1 - fp.minY();
                targetX = hitX - fp.centerX();
                targetZ = hitZ - fp.centerZ();
            }
            case "NORTH" -> targetZ = hitZ - 1 - fp.maxZ();
            case "SOUTH" -> targetZ = hitZ + 1 - fp.minZ();
            case "WEST" -> targetX = hitX - 1 - fp.maxX();
            case "EAST" -> targetX = hitX + 1 - fp.minX();
            default -> {
                /* keep support-centered defaults */
            }
        }

        int[] origin = {targetX, targetY, targetZ};
        if (footprintOverlapsPlayer(origin, fp, playerX, playerY, playerZ)) {
            return null;
        }
        return origin;
    }

    static boolean isUnderOrBesidePlayer(int hitX, int hitZ, int playerX, int playerZ) {
        return Math.max(Math.abs(hitX - playerX), Math.abs(hitZ - playerZ)) <= 1;
    }

    static boolean footprintOverlapsPlayer(
            int[] targetOrigin,
            Footprint fp,
            int playerX,
            int playerY,
            int playerZ
    ) {
        int worldMinX = targetOrigin[0] + fp.minX() - PLAYER_MARGIN;
        int worldMaxX = targetOrigin[0] + fp.maxX() + PLAYER_MARGIN;
        int worldMinY = targetOrigin[1] + fp.minY();
        int worldMaxY = targetOrigin[1] + fp.maxY();
        int worldMinZ = targetOrigin[2] + fp.minZ() - PLAYER_MARGIN;
        int worldMaxZ = targetOrigin[2] + fp.maxZ() + PLAYER_MARGIN;
        boolean horizontal = playerX >= worldMinX && playerX <= worldMaxX
                && playerZ >= worldMinZ && playerZ <= worldMaxZ;
        boolean vertical = playerY + 1 >= worldMinY && playerY <= worldMaxY;
        return horizontal && vertical;
    }
}
