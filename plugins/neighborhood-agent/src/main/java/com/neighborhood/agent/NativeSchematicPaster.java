package com.neighborhood.agent;

import com.sk89q.worldedit.EditSession;
import com.sk89q.worldedit.WorldEdit;
import com.sk89q.worldedit.bukkit.BukkitAdapter;
import com.sk89q.worldedit.extent.clipboard.Clipboard;
import com.sk89q.worldedit.extent.clipboard.io.ClipboardFormat;
import com.sk89q.worldedit.extent.clipboard.io.ClipboardFormats;
import com.sk89q.worldedit.extent.clipboard.io.ClipboardReader;
import com.sk89q.worldedit.function.operation.Operation;
import com.sk89q.worldedit.function.operation.Operations;
import com.sk89q.worldedit.math.BlockVector3;
import com.sk89q.worldedit.regions.Region;
import com.sk89q.worldedit.session.ClipboardHolder;
import com.sk89q.worldedit.world.block.BlockState;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.entity.Player;
import org.bukkit.plugin.Plugin;

import java.io.FileInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.regex.Pattern;

final class NativeSchematicPaster {
    private static final Pattern TEMPLATE_ID = Pattern.compile("^[a-z][a-z0-9_]{0,63}$");
    private static final int MAX_VOLUME = 200_000;

    private final NeighborhoodAgentPlugin plugin;
    private final BuildPolicy buildPolicy;
    private final TemplateCatalog catalog;

    NativeSchematicPaster(
            NeighborhoodAgentPlugin plugin,
            BuildPolicy buildPolicy,
            TemplateCatalog catalog
    ) {
        this.plugin = plugin;
        this.buildPolicy = buildPolicy;
        this.catalog = catalog;
    }

    LoadedTemplate load(String rawTemplateId) throws IOException {
        String templateId = rawTemplateId == null ? "" : rawTemplateId.trim();
        if (!TEMPLATE_ID.matcher(templateId).matches()) {
            throw new IllegalArgumentException("invalid template_id");
        }

        Plugin fawe = plugin.getServer().getPluginManager().getPlugin("FastAsyncWorldEdit");
        if (fawe == null || !fawe.isEnabled()) {
            throw new IllegalStateException("FastAsyncWorldEdit is not available");
        }

        Path root = fawe.getDataFolder().toPath()
                .resolve("schematics")
                .resolve("neighborhood")
                .toRealPath();
        Path requested = root.resolve(templateId + ".schem").normalize();
        if (!requested.startsWith(root) || !Files.isRegularFile(requested)) {
            throw new IllegalArgumentException("unknown template_id");
        }
        Path schematic = requested.toRealPath();
        if (!schematic.startsWith(root)) {
            throw new IllegalArgumentException("template path escapes the curated directory");
        }

        ClipboardFormat format = ClipboardFormats.findByFile(schematic.toFile());
        if (format == null) {
            throw new IOException("unsupported schematic format");
        }
        try (FileInputStream input = new FileInputStream(schematic.toFile());
             ClipboardReader reader = format.getReader(input)) {
            Clipboard clipboard = reader.read();
            long volume = clipboard.getRegion().getVolume();
            if (volume < 1 || volume > MAX_VOLUME) {
                clipboard.close();
                throw new IllegalArgumentException("template exceeds the 200,000 block safety limit");
            }
            return new LoadedTemplate(templateId, clipboard);
        }
    }

    PreparedPaste prepare(Player player, LoadedTemplate loaded) {
        if (!player.hasPermission("neighborhood.agent.build")) {
            loaded.close();
            throw new IllegalArgumentException("missing build permission");
        }

        Location playerLocation = player.getLocation();
        World bukkitWorld = player.getWorld();
        Clipboard clipboard = loaded.clipboard();
        SchematicPlacement.Footprint footprint = footprintOf(clipboard);
        OriginChoice choice = resolveSafeOrigin(player, playerLocation, footprint);
        if (choice == null || choice.origin() == null) {
            loaded.close();
            throw new PolicyDeniedException(SchematicPlacement.UNSAFE_MESSAGE);
        }
        BlockVector3 targetOrigin = choice.origin();
        // Hard gate: never paste when the footprint still covers the requester.
        if (SchematicPlacement.footprintOverlapsPlayer(
                new int[]{targetOrigin.x(), targetOrigin.y(), targetOrigin.z()},
                footprint,
                playerLocation.getBlockX(),
                playerLocation.getBlockY(),
                playerLocation.getBlockZ()
        )) {
            loaded.close();
            throw new PolicyDeniedException(SchematicPlacement.OVERLAP_MESSAGE);
        }
        // Ground-placed pastes need solid under the footprint. UP-face gaze
        // (roof/floor tops) already has a looked-at support surface — skip the
        // terrain majority check so upper-story placements aren't refused.
        if (!choice.supportedByUpFace()
                && !hasGroundSupport(bukkitWorld, targetOrigin, footprint)) {
            loaded.close();
            throw new PolicyDeniedException(SchematicPlacement.UNSAFE_MESSAGE);
        }

        BlockVector3 sourceOrigin = clipboard.getOrigin();
        BlockVector3 offset = targetOrigin.subtract(sourceOrigin);

        List<BuildPolicy.Placement> placements = new ArrayList<>();
        int nonAirBlocks = 0;
        for (BlockVector3 source : clipboard.getRegion()) {
            BlockState state = clipboard.getBlock(source);
            if (state.isAir()) {
                continue;
            }
            BlockVector3 target = source.add(offset);
            if (target.y() < bukkitWorld.getMinHeight() || target.y() >= bukkitWorld.getMaxHeight()) {
                loaded.close();
                throw new IllegalArgumentException("template would extend beyond the world's build height");
            }
            Material material = BukkitAdapter.adapt(state.getBlockType());
            placements.add(new BuildPolicy.Placement(
                    new Location(bukkitWorld, target.x(), target.y(), target.z()),
                    material
            ));
            nonAirBlocks++;
        }
        if (nonAirBlocks == 0) {
            loaded.close();
            throw new IllegalArgumentException("template contains no blocks");
        }

        String denied = buildPolicy.denyPlacements(player, placements);
        if (denied != null) {
            loaded.close();
            throw new PolicyDeniedException(denied);
        }
        return new PreparedPaste(
                loaded.templateId(),
                clipboard,
                BukkitAdapter.adapt(bukkitWorld),
                targetOrigin,
                nonAirBlocks,
                player.getUniqueId()
        );
    }

    PasteOutcome execute(PreparedPaste prepared, long started) {
        Clipboard clipboard = prepared.clipboard();
        EditSession completed = WorldEdit.getInstance()
                .newEditSessionBuilder()
                .world(prepared.world())
                .changeSet(true, prepared.playerId())
                .build();
        boolean sessionClosed = false;
        try {
            Operation operation = new ClipboardHolder(clipboard)
                    .createPaste(completed)
                    .to(prepared.targetOrigin())
                    .ignoreAirBlocks(true)
                    .copyEntities(false)
                    .copyBiomes(false)
                    .build();
            Operations.complete(operation);
            completed.flushQueue();
            completed.close();
            sessionClosed = true;

            boolean verified = verifyWithRetry(prepared);
            com.sk89q.worldedit.world.World world = prepared.world();
            UUID playerId = prepared.playerId();
            Runnable undo = () -> {
                try (EditSession undoSession = WorldEdit.getInstance()
                        .newEditSessionBuilder()
                        .world(world)
                        .changeSet(true, playerId)
                        .build()) {
                    completed.undo(undoSession);
                }
            };

            String title = catalog.titleFor(prepared.templateId());
            String message;
            if (verified) {
                message = "Built " + TemplateCatalog.withArticle(title)
                        + " nearby. Say “undo that” if you don’t like it.";
            } else {
                message = "I tried to build " + TemplateCatalog.withArticle(title)
                        + " nearby, but it didn’t look right, so check it before you keep it.";
            }
            return new PasteOutcome(
                    NativeToolRegistry.ToolResult.ok(message, verified, elapsedMs(started)),
                    undo,
                    prepared
            );
        } catch (Exception error) {
            throw new IllegalStateException("FAWE paste failed", error);
        } finally {
            if (!sessionClosed) {
                completed.close();
            }
            clipboard.close();
        }
    }

    private boolean verifyWithRetry(PreparedPaste prepared) {
        Verification last = verify(prepared);
        for (int attempt = 0; !last.ok() && attempt < 20; attempt++) {
            try {
                Thread.sleep(100L);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                break;
            }
            last = verify(prepared);
        }
        if (!last.ok()) {
            plugin.getLogger().warning(
                    "Template verification mismatch at " + last.point()
                            + ": expected=" + last.expected()
                            + " actual=" + last.actual()
            );
        }
        return last.ok();
    }

    private Verification verify(PreparedPaste prepared) {
        Clipboard clipboard = prepared.clipboard();
        BlockVector3 offset = prepared.targetOrigin().subtract(clipboard.getOrigin());
        for (BlockVector3 source : clipboard.getRegion()) {
            BlockState expected = clipboard.getBlock(source);
            if (expected.isAir()) {
                continue;
            }
            BlockVector3 target = source.add(offset);
            BlockState actual = prepared.world().getBlock(target);
            if (!expected.equals(actual)) {
                return new Verification(false, target, expected, actual);
            }
        }
        return new Verification(true, prepared.targetOrigin(), null, null);
    }

    private static OriginChoice resolveSafeOrigin(
            Player player,
            Location location,
            SchematicPlacement.Footprint footprint
    ) {
        int playerX = location.getBlockX();
        int playerY = location.getBlockY();
        int playerZ = location.getBlockZ();
        double dirX = location.getDirection().getX();
        double dirZ = location.getDirection().getZ();

        Integer hitX = null;
        Integer hitY = null;
        Integer hitZ = null;
        String face = null;
        Integer supportX = null;
        Integer supportY = null;
        Integer supportZ = null;
        if (player.isOnline()) {
            GazeHit hit = GazeSensor.capture(player);
            if (hit.hit() && hit.block() != null && hit.face() != null) {
                org.bukkit.block.Block support = hit.block().getRelative(hit.face());
                hitX = hit.block().getX();
                hitY = hit.block().getY();
                hitZ = hit.block().getZ();
                face = hit.face().name();
                supportX = support.getX();
                supportY = support.getY();
                supportZ = support.getZ();
            }
        }

        int[] origin = SchematicPlacement.resolveOrigin(
                playerX, playerY, playerZ, dirX, dirZ, footprint,
                hitX, hitY, hitZ, face, supportX, supportY, supportZ
        );
        if (origin == null) {
            return null;
        }
        boolean fromUpFace = false;
        if ("UP".equals(face) && hitX != null && hitY != null && hitZ != null
                && supportX != null && supportY != null && supportZ != null) {
            int[] gaze = SchematicPlacement.gazeAwareOrigin(
                    hitX, hitY, hitZ, face,
                    supportX, supportY, supportZ,
                    playerX, playerY, playerZ,
                    footprint
            );
            fromUpFace = gaze != null
                    && gaze[0] == origin[0]
                    && gaze[1] == origin[1]
                    && gaze[2] == origin[2];
        }
        return new OriginChoice(
                BlockVector3.at(origin[0], origin[1], origin[2]),
                fromUpFace
        );
    }

    /**
     * Sample corners + center under the footprint floor; require majority solid
     * so we don't paste floating or into empty air without ground.
     *
     * <p>"Support" means solid blocks under paste minY — not natural terrain.
     * A looked-at UP face (roof/floor top) is handled separately by the caller.
     */
    private static boolean hasGroundSupport(
            World world,
            BlockVector3 targetOrigin,
            SchematicPlacement.Footprint fp
    ) {
        int floorY = targetOrigin.y() + fp.minY() - 1;
        if (floorY < world.getMinHeight() || floorY >= world.getMaxHeight()) {
            return false;
        }
        int[] xs = {
                targetOrigin.x() + fp.minX(),
                targetOrigin.x() + fp.maxX(),
                targetOrigin.x() + fp.centerX()
        };
        int[] zs = {
                targetOrigin.z() + fp.minZ(),
                targetOrigin.z() + fp.maxZ(),
                targetOrigin.z() + fp.centerZ()
        };
        int solid = 0;
        int samples = 0;
        for (int x : xs) {
            for (int z : zs) {
                samples++;
                org.bukkit.block.Block block = world.getBlockAt(x, floorY, z);
                if (block.getType().isSolid() && !block.isPassable()) {
                    solid++;
                }
            }
        }
        return samples > 0 && solid * 2 >= samples;
    }

    private record OriginChoice(BlockVector3 origin, boolean supportedByUpFace) {
    }

    private static SchematicPlacement.Footprint footprintOf(Clipboard clipboard) {
        Region region = clipboard.getRegion();
        BlockVector3 origin = clipboard.getOrigin();
        BlockVector3 min = region.getMinimumPoint().subtract(origin);
        BlockVector3 max = region.getMaximumPoint().subtract(origin);
        return new SchematicPlacement.Footprint(
                min.x(), min.y(), min.z(), max.x(), max.y(), max.z()
        );
    }

    private static int elapsedMs(long started) {
        return (int) ((System.nanoTime() - started) / 1_000_000L);
    }

    record LoadedTemplate(String templateId, Clipboard clipboard) implements AutoCloseable {
        @Override
        public void close() {
            clipboard.close();
        }
    }

    record PreparedPaste(
            String templateId,
            Clipboard clipboard,
            com.sk89q.worldedit.world.World world,
            BlockVector3 targetOrigin,
            int nonAirBlocks,
            UUID playerId
    ) {
    }

    record PasteOutcome(
            NativeToolRegistry.ToolResult result,
            Runnable undo,
            PreparedPaste prepared
    ) {
    }

    private record Verification(
            boolean ok,
            BlockVector3 point,
            BlockState expected,
            BlockState actual
    ) {
    }

    static final class PolicyDeniedException extends IllegalArgumentException {
        PolicyDeniedException(String message) {
            super(message);
        }
    }
}
