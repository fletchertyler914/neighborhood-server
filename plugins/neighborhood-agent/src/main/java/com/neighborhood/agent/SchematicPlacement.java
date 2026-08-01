package com.neighborhood.agent;

/**
 * Pure paste-origin math for curated schematics.
 *
 * <p>WorldEdit pastes so clipboard origin lands at {@code targetOrigin}. Relative
 * footprint bounds are {@code regionMin/Max - clipboardOrigin}.
 *
 * <p>Policy: refuse-don't-build-bad. Never shift a bad origin and hope; callers
 * must skip the paste when {@link #resolveOrigin} returns null.
 */
final class SchematicPlacement {
    /** Extra blocks beyond half-footprint so the player stands clearly outside. */
    static final int PLAYER_MARGIN = 2;

    /** Gaze/facing could not find a clear paste origin. */
    static final String UNSAFE_MESSAGE =
            "I can't build there — look at an open spot and try again.";

    /** Footprint would cover the requesting player. */
    static final String OVERLAP_MESSAGE =
            "You're in the way — step aside and try again.";

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

        boolean valid() {
            return width() >= 1 && depth() >= 1 && height() >= 1;
        }
    }

    /**
     * Pick a paste origin: safe gaze first, else facing-offset with
     * half-footprint + margin clearance. Returns null when neither is safe.
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
            Integer supportZ
    ) {
        if (!fp.valid()) {
            return null;
        }
        if (hitX != null && hitY != null && hitZ != null && face != null
                && supportX != null && supportY != null && supportZ != null) {
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
        int[] facing = facingOffsetOrigin(playerX, playerY, playerZ, dirX, dirZ, fp);
        if (facing != null && !footprintOverlapsPlayer(facing, fp, playerX, playerY, playerZ)) {
            return facing;
        }
        return null;
    }

    /**
     * Near footprint edge is half-extent + {@link #PLAYER_MARGIN} in front of
     * the player (cardinal facing). Returns null if that still overlaps them.
     */
    static int[] facingOffsetOrigin(
            int playerX,
            int playerY,
            int playerZ,
            double dirX,
            double dirZ,
            Footprint fp
    ) {
        boolean alongX = Math.abs(dirX) > Math.abs(dirZ);
        int clearance = halfExtentClearance(fp, alongX);
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
        int targetY = playerY - 1 - fp.minY();
        int[] origin = {targetX, targetY, targetZ};
        if (footprintOverlapsPlayer(origin, fp, playerX, playerY, playerZ)) {
            return null;
        }
        return origin;
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
