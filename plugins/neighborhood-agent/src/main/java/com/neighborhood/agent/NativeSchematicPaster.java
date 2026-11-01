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
import com.sk89q.worldedit.world.block.BlockTypes;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.Tag;
import org.bukkit.World;
import org.bukkit.entity.Player;
import org.bukkit.plugin.Plugin;

import java.io.FileInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;

final class NativeSchematicPaster {
    private static final Pattern TEMPLATE_ID = Pattern.compile("^[a-z][a-z0-9_]{0,63}$");
    /** Default bbox volume cap — enough for ~160k+ filled mega curated pastes. */
    private static final int DEFAULT_MAX_VOLUME = 60_000_000;
    /** Cap GriefPrevention probes so mega pastes don't freeze the main thread. */
    private static final int MAX_CLAIM_SAMPLES = 2_048;
    /** Extra blocks around the footprint when clearing a pad. */
    private static final int CLEAR_MARGIN = 2;
    /** Extra height above schematic when clearing canopy / hills. */
    private static final int CLEAR_HEIGHT_PAD = 8;

    private static final Set<Material> NATURAL_TERRAIN = EnumSet.of(
            Material.GRASS_BLOCK,
            Material.DIRT,
            Material.COARSE_DIRT,
            Material.ROOTED_DIRT,
            Material.PODZOL,
            Material.MYCELIUM,
            Material.DIRT_PATH,
            Material.FARMLAND,
            Material.MUD,
            Material.MUDDY_MANGROVE_ROOTS,
            Material.STONE,
            Material.GRANITE,
            Material.DIORITE,
            Material.ANDESITE,
            Material.DEEPSLATE,
            Material.TUFF,
            Material.CALCITE,
            Material.DRIPSTONE_BLOCK,
            Material.SMOOTH_BASALT,
            Material.BASALT,
            Material.NETHERRACK,
            Material.END_STONE,
            Material.SAND,
            Material.RED_SAND,
            Material.GRAVEL,
            Material.CLAY,
            Material.TERRACOTTA,
            Material.SANDSTONE,
            Material.RED_SANDSTONE,
            Material.SNOW,
            Material.SNOW_BLOCK,
            Material.POWDER_SNOW,
            Material.ICE,
            Material.PACKED_ICE,
            Material.BLUE_ICE,
            Material.WATER,
            Material.LAVA,
            Material.SEAGRASS,
            Material.TALL_SEAGRASS,
            Material.KELP,
            Material.KELP_PLANT,
            Material.SUGAR_CANE,
            Material.CACTUS,
            Material.BAMBOO,
            Material.BAMBOO_SAPLING,
            Material.VINE,
            Material.GLOW_LICHEN,
            Material.MOSS_BLOCK,
            Material.MOSS_CARPET,
            Material.SHORT_GRASS,
            Material.TALL_GRASS,
            Material.FERN,
            Material.LARGE_FERN,
            Material.DEAD_BUSH,
            Material.BROWN_MUSHROOM,
            Material.RED_MUSHROOM,
            Material.CRIMSON_FUNGUS,
            Material.WARPED_FUNGUS,
            Material.CRIMSON_ROOTS,
            Material.WARPED_ROOTS,
            Material.NETHER_SPROUTS,
            Material.HANGING_ROOTS,
            Material.SPORE_BLOSSOM,
            Material.AZALEA,
            Material.FLOWERING_AZALEA,
            Material.SMALL_DRIPLEAF,
            Material.BIG_DRIPLEAF,
            Material.BIG_DRIPLEAF_STEM,
            Material.POINTED_DRIPSTONE,
            Material.COBBLESTONE,
            Material.MOSSY_COBBLESTONE,
            Material.BEDROCK
    );

    private final NeighborhoodAgentPlugin plugin;
    private final BuildPolicy buildPolicy;
    private final java.util.function.Supplier<TemplateCatalog> catalog;
    private final long maxVolume;

    NativeSchematicPaster(
            NeighborhoodAgentPlugin plugin,
            BuildPolicy buildPolicy,
            java.util.function.Supplier<TemplateCatalog> catalog
    ) {
        this.plugin = plugin;
        this.buildPolicy = buildPolicy;
        this.catalog = catalog;
        long configured = plugin.getConfig().getLong("max-paste-volume", DEFAULT_MAX_VOLUME);
        this.maxVolume = configured < 1 ? DEFAULT_MAX_VOLUME : configured;
    }

    private TemplateCatalog catalog() {
        return catalog.get();
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
            if (volume < 1 || volume > maxVolume) {
                clipboard.close();
                throw new IllegalArgumentException(
                        "template exceeds the " + maxVolume + " block paste volume limit"
                );
            }
            return new LoadedTemplate(templateId, clipboard);
        }
    }

    /**
     * Console/QA paste at a fixed stand pose (facing south). No player, no teleport,
     * no claim checks — remote campus only.
     */
    PreparedPaste prepareAt(
            World bukkitWorld,
            int standX,
            int standY,
            int standZ,
            LoadedTemplate loaded,
            boolean clearSite
    ) {
        Clipboard clipboard = loaded.clipboard();
        SchematicPlacement.Footprint footprint = footprintOf(clipboard);
        int[] origin = SchematicPlacement.facingOffsetOrigin(
                standX, standY, standZ, 0.0, 1.0, footprint, null
        );
        if (origin == null) {
            loaded.close();
            throw new PolicyDeniedException(SchematicPlacement.UNSAFE_MESSAGE);
        }
        BlockVector3 targetOrigin = BlockVector3.at(origin[0], origin[1], origin[2]);
        ClearMode clearMode = clearSite ? ClearMode.ALL : ClearMode.NONE;

        BlockVector3 sourceOrigin = clipboard.getOrigin();
        BlockVector3 offset = targetOrigin.subtract(sourceOrigin);
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
            nonAirBlocks++;
        }
        if (nonAirBlocks == 0) {
            loaded.close();
            throw new IllegalArgumentException("template contains no blocks");
        }

        // Stable console actor for FAWE changeset (not a real player).
        UUID qaActor = new UUID(0x4e484147454e54L, 0x51415041535445L);
        return new PreparedPaste(
                loaded.templateId(),
                clipboard,
                BukkitAdapter.adapt(bukkitWorld),
                targetOrigin,
                footprint,
                nonAirBlocks,
                qaActor,
                clearMode,
                null
        );
    }

    PreparedPaste prepare(
            Player player,
            LoadedTemplate loaded,
            boolean clearSite,
            Integer forwardBlocks
    ) {
        if (!player.hasPermission("neighborhood.agent.build")) {
            loaded.close();
            throw new IllegalArgumentException("missing build permission");
        }

        Location playerLocation = player.getLocation();
        World bukkitWorld = player.getWorld();
        Clipboard clipboard = loaded.clipboard();
        SchematicPlacement.Footprint footprint = footprintOf(clipboard);
        OriginChoice choice = resolveSafeOrigin(
                player, playerLocation, footprint, forwardBlocks
        );
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

        boolean groundOk = choice.supportedByUpFace()
                || hasGroundSupport(bukkitWorld, targetOrigin, footprint);
        boolean obstructed = hasObstructionsAboveFloor(
                bukkitWorld, targetOrigin, footprint
        );
        boolean needsClear = !groundOk || obstructed;
        // Never silent-clear. Ask first unless the player already opted in.
        if (needsClear && !clearSite) {
            loaded.close();
            throw new NeedsClearException(SchematicPlacement.CLEAR_ASK_MESSAGE);
        }
        ClearMode clearMode = clearSite ? ClearMode.ALL : ClearMode.NONE;

        BlockVector3 sourceOrigin = clipboard.getOrigin();
        BlockVector3 offset = targetOrigin.subtract(sourceOrigin);

        // Sample claim probes — full 155k+ scans freeze the main thread.
        long regionVolume = Math.max(1L, clipboard.getRegion().getVolume());
        int sampleStride = Math.max(1, (int) (regionVolume / MAX_CLAIM_SAMPLES));
        List<BuildPolicy.Placement> claimSamples = new ArrayList<>(MAX_CLAIM_SAMPLES);
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
            nonAirBlocks++;
            if (claimSamples.size() < MAX_CLAIM_SAMPLES
                    && (nonAirBlocks == 1 || (nonAirBlocks % sampleStride) == 0)) {
                Material material = BukkitAdapter.adapt(state.getBlockType());
                claimSamples.add(new BuildPolicy.Placement(
                        new Location(bukkitWorld, target.x(), target.y(), target.z()),
                        material
                ));
            }
        }
        if (nonAirBlocks == 0) {
            loaded.close();
            throw new IllegalArgumentException("template contains no blocks");
        }

        // Also probe the clear pad corners / center for claims.
        if (clearMode != ClearMode.NONE) {
            int floorY = targetOrigin.y() + footprint.minY();
            int minX = targetOrigin.x() + footprint.minX() - CLEAR_MARGIN;
            int maxX = targetOrigin.x() + footprint.maxX() + CLEAR_MARGIN;
            int minZ = targetOrigin.z() + footprint.minZ() - CLEAR_MARGIN;
            int maxZ = targetOrigin.z() + footprint.maxZ() + CLEAR_MARGIN;
            int[] xs = {minX, maxX, (minX + maxX) / 2};
            int[] zs = {minZ, maxZ, (minZ + maxZ) / 2};
            for (int x : xs) {
                for (int z : zs) {
                    claimSamples.add(new BuildPolicy.Placement(
                            new Location(bukkitWorld, x, floorY, z),
                            Material.AIR
                    ));
                }
            }
        }

        String denied = buildPolicy.denyPlacements(player, claimSamples);
        if (denied != null) {
            loaded.close();
            throw new PolicyDeniedException(denied);
        }

        String title = catalog().titleFor(loaded.templateId());
        String clearingMessage = null;
        if (clearMode != ClearMode.NONE) {
            clearingMessage = "Clearing some ground, then building "
                    + TemplateCatalog.withArticle(title) + " nearby…";
            if (player.isOnline()) {
                player.sendMessage(net.kyori.adventure.text.Component.text(
                        "[" + plugin.getDisplayName() + "] " + clearingMessage,
                        net.kyori.adventure.text.format.NamedTextColor.AQUA
                ));
            }
        }

        return new PreparedPaste(
                loaded.templateId(),
                clipboard,
                BukkitAdapter.adapt(bukkitWorld),
                targetOrigin,
                footprint,
                nonAirBlocks,
                player.getUniqueId(),
                clearMode,
                clearingMessage
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
            if (prepared.clearMode() != ClearMode.NONE) {
                clearPad(completed, prepared);
            }
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

            String title = catalog().titleFor(prepared.templateId());
            String message;
            if (verified) {
                if (prepared.clearMode() != ClearMode.NONE) {
                    message = "Cleared a pad and built " + TemplateCatalog.withArticle(title)
                            + " nearby. Say “undo that” if you don’t like it.";
                } else {
                    message = "Built " + TemplateCatalog.withArticle(title)
                            + " nearby. Say “undo that” if you don’t like it.";
                }
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

    /**
     * Clear air/obstructions in the paste volume from floor Y upward, then ensure
     * solid support directly under the floor. Never excavates below pad top
     * ({@code floorY - 1}); that support layer is fill-only.
     * Only runs after the player opted in ({@code clear_site}) or confirmed.
     */
    private static void clearPad(EditSession session, PreparedPaste prepared) throws Exception {
        SchematicPlacement.Footprint fp = prepared.footprint();
        BlockVector3 origin = prepared.targetOrigin();
        int minX = origin.x() + fp.minX() - CLEAR_MARGIN;
        int maxX = origin.x() + fp.maxX() + CLEAR_MARGIN;
        int minZ = origin.z() + fp.minZ() - CLEAR_MARGIN;
        int maxZ = origin.z() + fp.maxZ() + CLEAR_MARGIN;
        int floorY = origin.y() + fp.minY();
        int clearTop = Math.min(
                prepared.world().getMaxY(),
                floorY + fp.height() + CLEAR_HEIGHT_PAD
        );
        // Pad top / ground support — one below schem floor. Never air-clear here.
        int padY = floorY - 1;
        int worldMin = prepared.world().getMinY();
        if (padY < worldMin) {
            padY = worldMin;
        }

        BlockState air = BlockTypes.AIR.getDefaultState();
        BlockState dirt = BlockTypes.DIRT.getDefaultState();
        boolean clearAll = prepared.clearMode() == ClearMode.ALL;

        for (int x = minX; x <= maxX; x++) {
            for (int z = minZ; z <= maxZ; z++) {
                // Clear from floor upward only (pad+1 / schem volume). Never dig under pad top.
                for (int y = floorY; y <= clearTop; y++) {
                    BlockVector3 at = BlockVector3.at(x, y, z);
                    BlockState current = session.getBlock(at);
                    Material material = BukkitAdapter.adapt(current.getBlockType());
                    if (material == Material.BEDROCK || current.isAir()) {
                        continue;
                    }
                    if (clearAll || isNaturalTerrain(material)) {
                        session.setBlock(at, air);
                    }
                }
                if (padY >= worldMin && padY < floorY) {
                    BlockVector3 pad = BlockVector3.at(x, padY, z);
                    BlockState under = session.getBlock(pad);
                    Material underMat = BukkitAdapter.adapt(under.getBlockType());
                    if (underMat == Material.BEDROCK) {
                        continue;
                    }
                    // Fill-only support: solid pad top stays; air/non-solid becomes dirt.
                    if (under.isAir() || !underMat.isSolid()) {
                        session.setBlock(pad, dirt);
                    }
                }
            }
        }
    }

    /**
     * True when hills/trees/builds sit in the paste volume above the floor.
     * Flat grass under the floor alone does not count — normal pastes may
     * overwrite that without a clear pad.
     */
    private static boolean hasObstructionsAboveFloor(
            World world,
            BlockVector3 targetOrigin,
            SchematicPlacement.Footprint fp
    ) {
        int floorY = targetOrigin.y() + fp.minY();
        int topY = Math.min(
                world.getMaxHeight() - 1,
                floorY + Math.min(fp.height() + CLEAR_HEIGHT_PAD, 48)
        );
        if (floorY + 1 > topY) {
            return false;
        }
        int minX = targetOrigin.x() + fp.minX();
        int maxX = targetOrigin.x() + fp.maxX();
        int minZ = targetOrigin.z() + fp.minZ();
        int maxZ = targetOrigin.z() + fp.maxZ();
        int stride = Math.max(1, Math.max(fp.width(), fp.depth()) / 16);
        for (int x = minX; x <= maxX; x += stride) {
            for (int z = minZ; z <= maxZ; z += stride) {
                for (int y = floorY + 1; y <= topY; y += Math.max(1, stride)) {
                    org.bukkit.block.Block block = world.getBlockAt(x, y, z);
                    Material mat = block.getType();
                    if (mat.isAir() || mat == Material.BEDROCK) {
                        continue;
                    }
                    if (mat.isSolid() || Tag.LEAVES.isTagged(mat) || Tag.LOGS.isTagged(mat)
                            || Tag.REPLACEABLE.isTagged(mat)) {
                        return true;
                    }
                }
            }
        }
        return false;
    }

    static boolean isNaturalTerrain(Material material) {
        if (material == null || material.isAir()) {
            return true;
        }
        if (NATURAL_TERRAIN.contains(material)) {
            return true;
        }
        if (Tag.LEAVES.isTagged(material)
                || Tag.LOGS.isTagged(material)
                || Tag.SAPLINGS.isTagged(material)
                || Tag.FLOWERS.isTagged(material)
                || Tag.REPLACEABLE.isTagged(material)
                || Tag.BASE_STONE_OVERWORLD.isTagged(material)
                || Tag.BASE_STONE_NETHER.isTagged(material)
                || Tag.DIRT.isTagged(material)
                || Tag.TERRACOTTA.isTagged(material)
                || Tag.CROPS.isTagged(material)) {
            return true;
        }
        String key = material.getKey().getKey();
        return key.endsWith("_ore")
                || key.startsWith("potted_")
                || key.contains("coral")
                || key.endsWith("_nylium");
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
            SchematicPlacement.Footprint footprint,
            Integer forwardBlocks
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
                hitX, hitY, hitZ, face, supportX, supportY, supportZ,
                forwardBlocks
        );
        if (origin == null) {
            return null;
        }
        boolean fromUpFace = false;
        if ("UP".equals(face) && hitX != null && hitY != null && hitZ != null
                && supportX != null && supportY != null && supportZ != null
                && SchematicPlacement.gazeHitIsNearEnough(playerX, playerZ, hitX, hitZ, footprint)) {
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

    enum ClearMode {
        NONE,
        ALL
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
            SchematicPlacement.Footprint footprint,
            int nonAirBlocks,
            UUID playerId,
            ClearMode clearMode,
            String clearingMessage
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

    /** Site needs a clear/flatten pad; companion should ask before retrying. */
    static final class NeedsClearException extends IllegalArgumentException {
        NeedsClearException(String message) {
            super(message);
        }
    }
}
