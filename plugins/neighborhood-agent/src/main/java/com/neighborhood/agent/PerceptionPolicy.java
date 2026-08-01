package com.neighborhood.agent;

import org.bukkit.Material;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;

import java.util.List;

record PolicySnapshot(
        boolean canBuildAtTarget,
        boolean inClaim,
        boolean hasBuildPermission,
        String denyReason
) {
    static PolicySnapshot allow() {
        return new PolicySnapshot(true, false, true, null);
    }
}

final class PerceptionPolicy {
    private final BuildPolicy buildPolicy;

    PerceptionPolicy(BuildPolicy buildPolicy) {
        this.buildPolicy = buildPolicy;
    }

    PolicySnapshot probe(Player player, Block target) {
        boolean hasBuild = player.hasPermission("neighborhood.agent.build");
        if (!hasBuild) {
            return new PolicySnapshot(false, false, false, "I can't build here. Try: ask a grown-up for help.");
        }
        if (target == null) {
            return new PolicySnapshot(true, false, true, null);
        }
        Material material = target.getType().isAir() ? Material.STONE : target.getType();
        String denied = buildPolicy.denyReason(player, List.of(target.getLocation()), material);
        if (denied == null) {
            return new PolicySnapshot(true, false, true, null);
        }
        boolean claim = denied.toLowerCase().contains("claim");
        return new PolicySnapshot(false, claim, true, denied);
    }
}
