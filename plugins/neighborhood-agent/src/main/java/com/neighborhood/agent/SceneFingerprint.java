package com.neighborhood.agent;

import org.bukkit.Location;
import org.bukkit.block.Block;
import org.bukkit.block.BlockFace;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Locale;

final class SceneFingerprint {
    private SceneFingerprint() {
    }

    static String fast(Player player, Block gazeBlock, BlockFace face, ItemStack held) {
        Location loc = player.getLocation();
        String heldKey = held == null || held.getType().isAir() || !held.getType().isBlock()
                ? "air"
                : held.getType().getKey().getKey();
        String gazeKey = gazeBlock == null
                ? "miss"
                : gazeBlock.getX() + "," + gazeBlock.getY() + "," + gazeBlock.getZ()
                + ":" + gazeBlock.getType().getKey().getKey()
                + ":" + (face == null ? "none" : face.name().toLowerCase(Locale.ROOT));
        String raw = player.getWorld().getKey()
                + "|" + (int) Math.floor(loc.getX())
                + "," + (int) Math.floor(loc.getY())
                + "," + (int) Math.floor(loc.getZ())
                + "|" + Math.round(loc.getYaw())
                + "|" + Math.round(loc.getPitch())
                + "|" + gazeKey
                + "|" + heldKey;
        return sha256(raw).substring(0, 16);
    }

    static String geometry(
            String worldKey,
            int minX,
            int maxX,
            int minY,
            int maxY,
            int minZ,
            int maxZ,
            String materialHint,
            int airCells
    ) {
        String raw = worldKey + "|" + minX + "," + maxX + "," + minY + "," + maxY + ","
                + minZ + "," + maxZ + "|" + materialHint + "|" + airCells;
        return sha256(raw).substring(0, 16);
    }

    static boolean poseStale(Player player, double x, double y, double z, float yaw, float pitch) {
        Location loc = player.getLocation();
        double dx = loc.getX() - x;
        double dy = loc.getY() - y;
        double dz = loc.getZ() - z;
        double dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
        if (dist > PerceptionBudget.STALE_MOVE_BLOCKS) {
            return true;
        }
        float yawDelta = Math.abs(normalizeYaw(loc.getYaw()) - normalizeYaw(yaw));
        if (yawDelta > 180f) {
            yawDelta = 360f - yawDelta;
        }
        return yawDelta > PerceptionBudget.STALE_YAW_DEGREES
                || Math.abs(loc.getPitch() - pitch) > PerceptionBudget.STALE_YAW_DEGREES;
    }

    private static float normalizeYaw(float yaw) {
        float value = yaw % 360f;
        if (value < 0f) {
            value += 360f;
        }
        return value;
    }

    private static String sha256(String raw) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(raw.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException error) {
            return Integer.toHexString(raw.hashCode());
        }
    }
}
