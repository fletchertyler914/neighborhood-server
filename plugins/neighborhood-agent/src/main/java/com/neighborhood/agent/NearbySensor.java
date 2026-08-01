package com.neighborhood.agent;

import org.bukkit.block.Block;
import org.bukkit.entity.Entity;
import org.bukkit.entity.EntityType;
import org.bukkit.entity.LivingEntity;
import org.bukkit.entity.Monster;
import org.bukkit.entity.Player;

import java.util.Locale;
import java.util.Set;

record NearbyFacet(int friendlyCount, int hostileCount, String interactable) {
}

final class NearbySensor {
    private static final Set<EntityType> FRIENDLY = Set.of(
            EntityType.CHICKEN, EntityType.COW, EntityType.PIG, EntityType.SHEEP,
            EntityType.HORSE, EntityType.CAT, EntityType.WOLF, EntityType.RABBIT,
            EntityType.PARROT, EntityType.FOX, EntityType.VILLAGER
    );

    private NearbySensor() {
    }

    static NearbyFacet capture(Player player, GazeHit gaze) {
        int friendly = 0;
        int hostile = 0;
        for (Entity entity : player.getNearbyEntities(12, 8, 12)) {
            if (!(entity instanceof LivingEntity) || entity instanceof Player) {
                continue;
            }
            if (entity instanceof Monster || !FRIENDLY.contains(entity.getType())) {
                if (entity instanceof Monster) {
                    hostile++;
                }
            } else {
                friendly++;
            }
        }
        String interactable = null;
        if (gaze.hit() && gaze.block() != null) {
            interactable = classify(gaze.block());
        }
        return new NearbyFacet(friendly, hostile, interactable);
    }

    private static String classify(Block block) {
        String key = block.getType().getKey().getKey().toLowerCase(Locale.ROOT);
        if (key.contains("chest") || key.contains("barrel") || key.contains("shulker")) {
            return "chest";
        }
        if (key.contains("door")) {
            return "door";
        }
        if (key.contains("button")) {
            return "button";
        }
        if (key.contains("lever")) {
            return "lever";
        }
        if (key.contains("sign")) {
            return "sign";
        }
        return null;
    }
}
