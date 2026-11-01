package com.neighborhood.agent;

import com.sk89q.worldedit.EditSession;
import com.sk89q.worldedit.WorldEdit;
import com.sk89q.worldedit.bukkit.BukkitAdapter;
import com.sk89q.worldedit.math.BlockVector3;
import com.sk89q.worldedit.world.block.BlockState;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.block.data.BlockData;

import java.util.List;
import java.util.UUID;

/** Applies a pre-approved bounded block set through FAWE and exposes its change-set undo. */
final class BoundedFaweEdit {
    private BoundedFaweEdit() {
    }

    static Runnable apply(World world, UUID playerId, List<Block> blocks, Material material) {
        return applyMixed(world, playerId, blocks, material, List.of());
    }

    /**
     * Air-clear {@code clearBlocks}, then place {@code material} on {@code setBlocks}
     * in one FAWE changeset (single undo). Clear runs first so shared coords
     * (e.g. gold path markers on the walk surface) end as the intended material.
     */
    static Runnable applyMixed(
            World world,
            UUID playerId,
            List<Block> setBlocks,
            Material material,
            List<Block> clearBlocks
    ) {
        return applyMixed(world, playerId, setBlocks, material.createBlockData(), clearBlocks);
    }

    /** Same as material overload, but preserves facing/half for stairs etc. */
    static Runnable applyMixed(
            World world,
            UUID playerId,
            List<Block> setBlocks,
            BlockData data,
            List<Block> clearBlocks
    ) {
        EditSession completed = WorldEdit.getInstance()
                .newEditSessionBuilder()
                .world(BukkitAdapter.adapt(world))
                .changeSet(true, playerId)
                .build();
        try {
            BlockState state = BukkitAdapter.adapt(data);
            BlockState air = BukkitAdapter.adapt(Material.AIR.createBlockData());
            for (Block block : clearBlocks) {
                completed.setBlock(
                        BlockVector3.at(block.getX(), block.getY(), block.getZ()),
                        air
                );
            }
            for (Block block : setBlocks) {
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
