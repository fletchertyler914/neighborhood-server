package com.neighborhood.agent;

import org.bukkit.FluidCollisionMode;
import org.bukkit.block.Block;
import org.bukkit.block.BlockFace;
import org.bukkit.entity.Player;
import org.bukkit.util.RayTraceResult;

record GazeHit(boolean hit, Block block, BlockFace face, double distance) {
    static GazeHit miss() {
        return new GazeHit(false, null, null, 0.0);
    }
}

final class GazeSensor {
    private GazeSensor() {
    }

    static GazeHit capture(Player player) {
        RayTraceResult ray = player.rayTraceBlocks(
                PerceptionBudget.GAZE_RAY_BLOCKS,
                FluidCollisionMode.NEVER
        );
        if (ray == null || ray.getHitBlock() == null) {
            return GazeHit.miss();
        }
        BlockFace face = ray.getHitBlockFace();
        double distance = ray.getHitPosition() == null
                ? player.getEyeLocation().distance(ray.getHitBlock().getLocation().add(0.5, 0.5, 0.5))
                : player.getEyeLocation().toVector().distance(ray.getHitPosition());
        return new GazeHit(true, ray.getHitBlock(), face, distance);
    }
}
