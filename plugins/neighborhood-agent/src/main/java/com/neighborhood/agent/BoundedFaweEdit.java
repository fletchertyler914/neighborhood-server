package com.neighborhood.agent;

import com.sk89q.worldedit.EditSession;
import com.sk89q.worldedit.WorldEdit;
import com.sk89q.worldedit.bukkit.BukkitAdapter;
import com.sk89q.worldedit.math.BlockVector3;
import com.sk89q.worldedit.world.block.BlockState;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.block.Block;

import java.util.List;
import java.util.UUID;

/** Applies a pre-approved bounded block set through FAWE and exposes its change-set undo. */
final class BoundedFaweEdit {
    private BoundedFaweEdit() {
    }

    static Runnable apply(World world, UUID playerId, List<Block> blocks, Material material) {
        EditSession completed = WorldEdit.getInstance()
                .newEditSessionBuilder()
                .world(BukkitAdapter.adapt(world))
                .changeSet(true, playerId)
                .build();
        try {
            BlockState state = BukkitAdapter.adapt(material.createBlockData());
            for (Block block : blocks) {
                completed.setBlock(
                        BlockVector3.at(block.getX(), block.getY(), block.getZ()),
                        state
                );
            }
            completed.flushQueue();
            completed.close();
        } catch (Exception error) {
            completed.close();
            throw new IllegalStateException("FAWE edit failed", error);
        }
        return () -> {
            try (EditSession undoSession = WorldEdit.getInstance()
                    .newEditSessionBuilder()
                    .world(BukkitAdapter.adapt(world))
                    .changeSet(true, playerId)
                    .build()) {
                completed.undo(undoSession);
            }
        };
    }
}
