package com.neighborhood.agent;

import com.google.gson.JsonObject;
import org.bukkit.Material;
import org.bukkit.FluidCollisionMode;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.entity.EntityType;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Supplier;

final class NativeToolRegistry {
    private static final Set<String> CAPABILITIES = Set.of(
            "set_time",
            "set_weather",
            "give_item",
            "summon_entity",
            "undo_last",
            "finish_wall",
            "finish_floor",
            "paste_template",
            "place_shape"
    );

    @FunctionalInterface
    interface WallFinisher {
        ToolResult finish(Player player, JsonObject arguments, long started);
    }
    private static final int MAX_FLOOR_CELLS = 2_500;
    private static final Set<EntityType> FRIENDLY_ENTITIES = Set.of(
            EntityType.CHICKEN,
            EntityType.COW,
            EntityType.PIG,
            EntityType.SHEEP,
            EntityType.HORSE,
            EntityType.WOLF,
            EntityType.CAT,
            EntityType.RABBIT,
            EntityType.GOAT,
            EntityType.FOX,
            EntityType.FROG,
            EntityType.BEE,
            EntityType.ALLAY,
            EntityType.CAMEL,
            EntityType.ARMADILLO
    );
    private static final Set<Material> RESTRICTED_ITEMS = Set.of(
            Material.COMMAND_BLOCK,
            Material.CHAIN_COMMAND_BLOCK,
            Material.REPEATING_COMMAND_BLOCK,
            Material.STRUCTURE_BLOCK,
            Material.JIGSAW,
            Material.DEBUG_STICK,
            Material.BARRIER,
            Material.BEDROCK,
            Material.TNT,
            Material.LAVA_BUCKET,
            Material.FIRE_CHARGE,
            Material.FLINT_AND_STEEL,
            Material.END_CRYSTAL
    );
    private static final long UNDO_TTL_MS = 600_000L;
    private static final int MAX_WALL_HEIGHT = 128;
    private static final int MAX_WALL_CELLS = 8_000;
    private final Map<UUID, UndoAction> undo = new ConcurrentHashMap<>();
    private final NeighborhoodAgentPlugin plugin;
    private final BuildPolicy buildPolicy;
    private final NativeSchematicPaster schematicPaster;
    private final PerceptionEngine perception;
    private final TemplateCatalog catalog;
    private final PlaceShapeExecutor placeShapeExecutor;

    NativeToolRegistry(
            NeighborhoodAgentPlugin plugin,
            PerceptionEngine perception,
            BuildPolicy buildPolicy
    ) {
        this.plugin = plugin;
        this.perception = perception;
        this.buildPolicy = buildPolicy;
        this.catalog = TemplateCatalog.load(
                plugin.getDataFolder().toPath().resolve("catalog.json"),
                plugin.getLogger()
        );
        this.schematicPaster = new NativeSchematicPaster(plugin, buildPolicy, catalog);
        this.placeShapeExecutor = new PlaceShapeExecutor(
                buildPolicy,
                perception,
                this::rememberUndo,
                this::finishWall
        );
    }

    List<String> capabilities() {
        return CAPABILITIES.stream().sorted().toList();
    }

    ToolResult execute(Player player, String tool, JsonObject arguments) {
        long started = System.nanoTime();
        try {
            return switch (tool) {
                case "set_time" -> setTime(player, arguments, started);
                case "set_weather" -> setWeather(player, arguments, started);
                case "give_item" -> giveItem(player, arguments, started);
                case "summon_entity" -> summonEntity(player, arguments, started);
                case "undo_last" -> undoLast(player, started);
                case "finish_wall" -> finishWall(player, arguments, started);
                case "finish_floor" -> finishFloor(player, arguments, started);
                case "place_shape" -> placeShapeExecutor.execute(player, arguments, started);
                default -> ToolResult.fail("That ability is not installed.", elapsedMs(started));
            };
        } catch (IllegalArgumentException exception) {
            return ToolResult.fail("I couldn't understand those details.", elapsedMs(started));
        } catch (Exception exception) {
            return ToolResult.fail("I couldn't finish that safely.", elapsedMs(started));
        }
    }

    CompletableFuture<ToolResult> executeAsync(Player player, String tool, JsonObject arguments) {
        if (!"paste_template".equals(tool)) {
            return CompletableFuture.completedFuture(execute(player, tool, arguments));
        }
        long started = System.nanoTime();
        final String templateId;
        try {
            templateId = requiredString(arguments, "template_id");
        } catch (IllegalArgumentException error) {
            return CompletableFuture.completedFuture(
                    ToolResult.fail("I couldn't understand that template name.", elapsedMs(started))
            );
        }

        return CompletableFuture
                .supplyAsync(() -> {
                    try {
                        return schematicPaster.load(templateId);
                    } catch (Exception error) {
                        throw new CompletionException(error);
                    }
                })
                .thenCompose(loaded -> onMainThread(() -> schematicPaster.prepare(player, loaded)))
                .thenApplyAsync(prepared -> schematicPaster.execute(prepared, started))
                .thenCompose(outcome -> onMainThreadResult(() -> finalizePaste(player, outcome, started)))
                .exceptionally(error -> pasteFailure(error, started));
    }

    private ToolResult finalizePaste(
            Player player,
            NativeSchematicPaster.PasteOutcome outcome,
            long started
    ) {
        ToolResult result = outcome.result();
        List<UUID> spawned = new ArrayList<>();
        if (result.verified() && player.isOnline()) {
            spawned.addAll(runPasteFollowUps(player, outcome.prepared()));
        }
        Runnable pasteUndo = outcome.undo();
        rememberUndo(player, () -> {
            pasteUndo.run();
            for (UUID id : spawned) {
                var entity = player.getWorld().getEntity(id);
                if (entity != null) {
                    entity.remove();
                }
            }
        });
        if (spawned.isEmpty()) {
            return result;
        }
        String animal = catalog.followUpsFor(outcome.prepared().templateId()).stream()
                .findFirst()
                .map(TemplateCatalog.FollowUpSummon::entity)
                .orElse("animals")
                .replace('_', ' ');
        String plural = animal.endsWith("s") ? animal : animal + "s";
        String message = result.message().replace(
                ". Say “undo that”",
                " and added some " + plural + ". Say “undo that”"
        );
        if (message.equals(result.message())) {
            message = result.message() + " Added some " + plural + " too.";
        }
        return ToolResult.ok(message, result.verified(), elapsedMs(started));
    }

    private List<UUID> runPasteFollowUps(
            Player player,
            NativeSchematicPaster.PreparedPaste prepared
    ) {
        List<UUID> spawned = new ArrayList<>();
        if (!player.hasPermission("neighborhood.agent.mobs")) {
            return spawned;
        }
        Location spawnAt = new Location(
                player.getWorld(),
                prepared.targetOrigin().x() + 0.5,
                prepared.targetOrigin().y() + 1,
                prepared.targetOrigin().z() + 0.5
        );
        for (TemplateCatalog.FollowUpSummon step : catalog.followUpsFor(prepared.templateId())) {
            EntityType type;
            try {
                type = EntityType.valueOf(step.entity().toUpperCase(Locale.ROOT));
            } catch (IllegalArgumentException ignored) {
                continue;
            }
            if (!type.isSpawnable() || !type.isAlive() || !FRIENDLY_ENTITIES.contains(type)) {
                continue;
            }
            Location at = spawnAt.clone().add(0, Math.max(0, step.offsetY() - 1), 0);
            for (int i = 0; i < step.count(); i++) {
                spawned.add(player.getWorld().spawnEntity(at, type).getUniqueId());
            }
        }
        return spawned;
    }

    private CompletableFuture<ToolResult> onMainThreadResult(Supplier<ToolResult> action) {
        CompletableFuture<ToolResult> future = new CompletableFuture<>();
        plugin.getServer().getScheduler().runTask(plugin, () -> {
            try {
                future.complete(action.get());
            } catch (Throwable error) {
                future.completeExceptionally(error);
            }
        });
        return future;
    }

    private CompletableFuture<NativeSchematicPaster.PreparedPaste> onMainThread(
            Supplier<NativeSchematicPaster.PreparedPaste> action
    ) {
        CompletableFuture<NativeSchematicPaster.PreparedPaste> future = new CompletableFuture<>();
        plugin.getServer().getScheduler().runTask(plugin, () -> {
            try {
                future.complete(action.get());
            } catch (Throwable error) {
                future.completeExceptionally(error);
            }
        });
        return future;
    }

    private ToolResult pasteFailure(Throwable error, long started) {
        Throwable cause = error;
        while ((cause instanceof CompletionException || cause instanceof java.util.concurrent.ExecutionException)
                && cause.getCause() != null) {
            cause = cause.getCause();
        }
        if (cause instanceof NativeSchematicPaster.PolicyDeniedException) {
            return ToolResult.fail(cause.getMessage(), elapsedMs(started));
        }
        if (cause instanceof IllegalArgumentException) {
            return ToolResult.fail(
                    "That template isn't available or can't be pasted safely there.",
                    elapsedMs(started)
            );
        }
        plugin.getLogger().warning("Native schematic paste failed: " + cause.getMessage());
        return ToolResult.fail("I couldn't paste that template safely.", elapsedMs(started));
    }

    private ToolResult setTime(Player player, JsonObject arguments, long started) {
        if (!player.hasPermission("neighborhood.agent.world")) {
            return ToolResult.fail(
                    "I can't change the time here. Try: ask a grown-up for help.",
                    elapsedMs(started)
            );
        }
        String value = requiredString(arguments, "time");
        long ticks = switch (value) {
            case "day" -> 1000L;
            case "noon" -> 6000L;
            case "night" -> 13000L;
            case "midnight" -> 18000L;
            default -> throw new IllegalArgumentException("unsupported time");
        };
        World world = player.getWorld();
        long previous = world.getTime();
        world.setTime(ticks);
        boolean verified = world.getTime() == ticks;
        if (verified) {
            rememberUndo(player, () -> world.setTime(previous));
        }
        String label = switch (value) {
            case "day" -> "daytime";
            case "night" -> "nighttime";
            default -> value;
        };
        return ToolResult.ok("Made it " + label + ".", verified, elapsedMs(started));
    }

    private ToolResult setWeather(Player player, JsonObject arguments, long started) {
        if (!player.hasPermission("neighborhood.agent.world")) {
            return ToolResult.fail(
                    "I can't change the weather here. Try: ask a grown-up for help.",
                    elapsedMs(started)
            );
        }
        String value = requiredString(arguments, "weather");
        World world = player.getWorld();
        boolean previousStorm = world.hasStorm();
        boolean previousThunder = world.isThundering();
        switch (value) {
            case "clear" -> {
                world.setStorm(false);
                world.setThundering(false);
            }
            case "rain" -> {
                world.setStorm(true);
                world.setThundering(false);
            }
            case "thunder" -> {
                world.setStorm(true);
                world.setThundering(true);
            }
            default -> throw new IllegalArgumentException("unsupported weather");
        }
        boolean verified = switch (value) {
            case "clear" -> !world.hasStorm() && !world.isThundering();
            case "rain" -> world.hasStorm() && !world.isThundering();
            case "thunder" -> world.hasStorm() && world.isThundering();
            default -> false;
        };
        if (verified) {
            rememberUndo(player, () -> {
                world.setStorm(previousStorm);
                world.setThundering(previousThunder);
            });
        }
        String message = value.equals("clear") ? "Cleared the weather." : "Made the weather " + value + ".";
        return ToolResult.ok(message, verified, elapsedMs(started));
    }

    private ToolResult giveItem(Player player, JsonObject arguments, long started) {
        if (!player.hasPermission("neighborhood.agent.inventory")) {
            return ToolResult.fail(
                    "I can't give items here. Try: ask a grown-up for help.",
                    elapsedMs(started)
            );
        }
        String materialName = requiredString(arguments, "material");
        int amount = requiredInt(arguments, "amount", 1, 64);
        Material material = Material.matchMaterial(materialName);
        if (material == null || !material.isItem() || material.isAir()) {
            return ToolResult.fail("I don't know that Minecraft item.", elapsedMs(started));
        }
        if (RESTRICTED_ITEMS.contains(material)) {
            return ToolResult.fail("I can’t give out that item safely.", elapsedMs(started));
        }
        var leftovers = player.getInventory().addItem(new ItemStack(material, amount));
        if (!leftovers.isEmpty()) {
            return ToolResult.fail("Your inventory is too full for all of that.", elapsedMs(started));
        }
        rememberUndo(player, () -> player.getInventory().removeItem(new ItemStack(material, amount)));
        String readable = material.getKey().getKey().replace('_', ' ');
        return ToolResult.ok("Gave you " + amount + " " + readable + ".", true, elapsedMs(started));
    }

    private ToolResult summonEntity(Player player, JsonObject arguments, long started) {
        if (!player.hasPermission("neighborhood.agent.mobs")) {
            return ToolResult.fail(
                    "I can't summon animals here. Try: ask a grown-up for help.",
                    elapsedMs(started)
            );
        }
        String entityName = requiredString(arguments, "entity").toUpperCase(Locale.ROOT);
        int count = requiredInt(arguments, "count", 1, 20);
        EntityType type = EntityType.valueOf(entityName);
        if (!type.isSpawnable() || !type.isAlive() || !FRIENDLY_ENTITIES.contains(type)) {
            return ToolResult.fail("I can only summon friendly animals.", elapsedMs(started));
        }
        List<UUID> spawned = new ArrayList<>();
        for (int i = 0; i < count; i++) {
            spawned.add(player.getWorld().spawnEntity(player.getLocation(), type).getUniqueId());
        }
        rememberUndo(player, () -> spawned.forEach(id -> {
            var entity = player.getWorld().getEntity(id);
            if (entity != null) {
                entity.remove();
            }
        }));
        String readable = type.getKey().getKey().replace('_', ' ');
        return ToolResult.ok("Summoned " + count + " " + readable + (count == 1 ? "." : "s."), true, elapsedMs(started));
    }

    private ToolResult undoLast(Player player, long started) {
        if (!player.hasPermission("neighborhood.agent.undo")) {
            return ToolResult.fail(
                    "I can't undo here. Try: ask a grown-up for help.",
                    elapsedMs(started)
            );
        }
        UUID playerId = player.getUniqueId();
        UndoAction action = undo.get(playerId);
        if (action == null) {
            return ToolResult.fail("There isn’t a recent sidekick action to undo.", elapsedMs(started));
        }
        if (System.currentTimeMillis() - action.createdAtMs() > UNDO_TTL_MS) {
            undo.remove(playerId, action);
            return ToolResult.fail("That sidekick action is more than 10 minutes old, so I can’t undo it safely.", elapsedMs(started));
        }
        action.rollback().run();
        undo.remove(playerId, action);
        return ToolResult.ok("Undid my last action.", true, elapsedMs(started));
    }

    private ToolResult finishWall(Player player, JsonObject arguments, long started) {
        if (!player.hasPermission("neighborhood.agent.build")) {
            return ToolResult.fail("I can't build here. Try: ask a grown-up for help.", elapsedMs(started));
        }
        Integer requestedHeight = optionalInt(arguments, "height", 0, MAX_WALL_HEIGHT);
        String requestedMaterial = optionalString(arguments, "material");
        GeometryResult geometry = perception.inspectGeometry(player, "finish_wall");
        OpeningFacet opening = geometry.openings().isEmpty() ? null : geometry.openings().get(0);

        // Fallback: legacy two matching posts when opening confidence is low/absent.
        if (opening == null || "none".equals(opening.confidence()) || "low".equals(opening.confidence())) {
            ToolResult legacy = finishWallLegacy(
                    player, requestedHeight, requestedMaterial, started
            );
            if (legacy != null) {
                return legacy;
            }
            if (opening == null) {
                return ToolResult.fail(
                        "I couldn't find an open wall face. Try: look at a corner and ask again.",
                        elapsedMs(started)
                );
            }
        }

        Material material = resolveWallMaterial(player, requestedMaterial, opening);
        if (material == null) {
            return ToolResult.fail(
                    "Hold the block you want, or say the material. Try: finish this wall with quartz",
                    elapsedMs(started)
            );
        }
        if (RESTRICTED_ITEMS.contains(material)) {
            return ToolResult.fail("I can’t use that block safely.", elapsedMs(started));
        }

        int height = requestedHeight != null && requestedHeight >= 2
                ? requestedHeight
                : opening.height();
        if (height < 2) {
            return ToolResult.fail(
                    "How tall should it be? Try: finish this wall 12 blocks high",
                    elapsedMs(started)
            );
        }
        height = Math.min(height, MAX_WALL_HEIGHT);

        boolean alongX = "x".equals(opening.axis());
        int baseY = opening.minY();
        int minX = opening.minX();
        int maxX = opening.maxX();
        int minZ = opening.minZ();
        int maxZ = opening.maxZ();
        int length = opening.length();
        World world = player.getWorld();

        List<Block> changes = new ArrayList<>();
        for (int y = baseY; y < baseY + height; y++) {
            if (y < world.getMinHeight() || y >= world.getMaxHeight()) {
                continue;
            }
            if (alongX) {
                for (int x = minX; x <= maxX; x++) {
                    Block block = world.getBlockAt(x, y, minZ);
                    if (block.getType().isAir()) {
                        changes.add(block);
                    }
                }
            } else {
                for (int z = minZ; z <= maxZ; z++) {
                    Block block = world.getBlockAt(minX, y, z);
                    if (block.getType().isAir()) {
                        changes.add(block);
                    }
                }
            }
        }
        if (changes.isEmpty()) {
            return ToolResult.ok(
                    "That " + length + "×" + height + " wall is already filled in.",
                    true,
                    elapsedMs(started)
            );
        }
        if (changes.size() > MAX_WALL_CELLS) {
            return ToolResult.fail(
                    "That wall is too big to finish safely in one go. Try a shorter height.",
                    elapsedMs(started)
            );
        }
        List<Location> locations = changes.stream().map(Block::getLocation).toList();
        String denied = buildPolicy.denyReason(player, locations, material);
        if (denied != null) {
            return ToolResult.fail(denied, elapsedMs(started));
        }
        Runnable undo = BoundedFaweEdit.apply(
                world, player.getUniqueId(), changes, material
        );
        boolean verified = changes.stream().allMatch(block -> block.getType() == material);
        if (verified) {
            rememberUndo(player, undo);
        } else {
            undo.run();
            return ToolResult.fail(
                    "I couldn't finish that wall exactly, so I put things back.",
                    elapsedMs(started)
            );
        }
        String readable = material.getKey().getKey().replace('_', ' ');
        return ToolResult.ok(
                "Finished your " + readable + " wall (" + height + " tall, " + length
                        + " long). Say “undo that” if you don’t like it.",
                true,
                elapsedMs(started)
        );
    }

    private ToolResult finishWallLegacy(
            Player player,
            Integer requestedHeight,
            String requestedMaterial,
            long started
    ) {
        Material fillMaterial = null;
        if (requestedMaterial != null && !requestedMaterial.isBlank()) {
            fillMaterial = Material.matchMaterial(
                    requestedMaterial.toLowerCase(Locale.ROOT).replace("minecraft:", "")
            );
        }
        if (fillMaterial == null || !fillMaterial.isBlock() || fillMaterial.isAir()) {
            ItemStack held = player.getInventory().getItemInMainHand();
            if (held != null && held.getType().isBlock() && !held.getType().isAir()) {
                fillMaterial = held.getType();
            }
        }

        Block start = null;
        Material postMaterial = null;
        GazeHit gaze = GazeSensor.capture(player);
        if (gaze.hit() && gaze.block() != null
                && !gaze.block().getType().isAir()
                && gaze.block().getType().isBlock()) {
            start = gaze.block();
            postMaterial = start.getType();
        }
        // Gaze often hits the floor between posts (pitch down). Walk the look
        // axis for freestanding matching posts of the fill/held material.
        if (start == null || findWallCandidate(player, start, postMaterial) == null) {
            Material probe = fillMaterial != null ? fillMaterial : postMaterial;
            Block scanned = findPostAlongLook(player, probe);
            if (scanned != null) {
                start = scanned;
                postMaterial = scanned.getType();
            }
        }
        if (start == null || postMaterial == null || postMaterial.isAir()) {
            return null;
        }
        if (fillMaterial == null || !fillMaterial.isBlock() || fillMaterial.isAir()) {
            fillMaterial = postMaterial;
        }
        final Material placed = fillMaterial;
        WallCandidate candidate = findWallCandidate(player, start, postMaterial);
        if (candidate == null) {
            return null;
        }
        int height = requestedHeight != null && requestedHeight >= 2 ? requestedHeight : 8;
        height = Math.min(height, MAX_WALL_HEIGHT);
        Block end = candidate.end();
        boolean alongX = start.getZ() == end.getZ();
        int baseY = Math.min(start.getY(), end.getY());
        int minX = Math.min(start.getX(), end.getX());
        int maxX = Math.max(start.getX(), end.getX());
        int minZ = Math.min(start.getZ(), end.getZ());
        int maxZ = Math.max(start.getZ(), end.getZ());
        int length = alongX ? (maxX - minX + 1) : (maxZ - minZ + 1);
        List<Block> changes = new ArrayList<>();
        for (int y = baseY; y < baseY + height; y++) {
            if (alongX) {
                for (int x = minX; x <= maxX; x++) {
                    Block block = start.getWorld().getBlockAt(x, y, minZ);
                    if (block.getType().isAir()) {
                        changes.add(block);
                    }
                }
            } else {
                for (int z = minZ; z <= maxZ; z++) {
                    Block block = start.getWorld().getBlockAt(minX, y, z);
                    if (block.getType().isAir()) {
                        changes.add(block);
                    }
                }
            }
        }
        if (changes.isEmpty() || changes.size() > MAX_WALL_CELLS) {
            return null;
        }
        String denied = buildPolicy.denyReason(
                player,
                changes.stream().map(Block::getLocation).toList(),
                placed
        );
        if (denied != null) {
            return ToolResult.fail(denied, elapsedMs(started));
        }
        Runnable undo = BoundedFaweEdit.apply(
                player.getWorld(), player.getUniqueId(), changes, placed
        );
        boolean verified = changes.stream().allMatch(block -> block.getType() == placed);
        if (!verified) {
            undo.run();
            return null;
        }
        rememberUndo(player, undo);
        String readable = placed.getKey().getKey().replace('_', ' ');
        return ToolResult.ok(
                "Finished your " + readable + " wall (" + height + " tall, " + length
                        + " long). Say “undo that” if you don’t like it.",
                true,
                elapsedMs(started)
        );
    }

    /** Find a freestanding post of the preferred material along the look axis. */
    private static Block findPostAlongLook(Player player, Material preferred) {
        if (preferred == null || preferred.isAir() || !preferred.isBlock()) {
            return null;
        }
        var direction = player.getLocation().getDirection().clone().setY(0);
        if (direction.lengthSquared() < 1.0e-6) {
            return null;
        }
        direction.normalize();
        int startX = player.getLocation().getBlockX();
        int startY = player.getLocation().getBlockY();
        int startZ = player.getLocation().getBlockZ();
        World world = player.getWorld();
        for (int distance = 1; distance <= 10; distance++) {
            int x = startX + (int) Math.round(direction.getX() * distance);
            int z = startZ + (int) Math.round(direction.getZ() * distance);
            for (int dy = 0; dy <= 3; dy++) {
                Block block = world.getBlockAt(x, startY + dy, z);
                if (block.getType() != preferred) {
                    continue;
                }
                int solidNeighbors = 0;
                if (!block.getRelative(1, 0, 0).getType().isAir()
                        && block.getRelative(1, 0, 0).getType().isSolid()) {
                    solidNeighbors++;
                }
                if (!block.getRelative(-1, 0, 0).getType().isAir()
                        && block.getRelative(-1, 0, 0).getType().isSolid()) {
                    solidNeighbors++;
                }
                if (!block.getRelative(0, 0, 1).getType().isAir()
                        && block.getRelative(0, 0, 1).getType().isSolid()) {
                    solidNeighbors++;
                }
                if (!block.getRelative(0, 0, -1).getType().isAir()
                        && block.getRelative(0, 0, -1).getType().isSolid()) {
                    solidNeighbors++;
                }
                if (solidNeighbors <= 1) {
                    return block;
                }
            }
        }
        return null;
    }

    private ToolResult finishFloor(Player player, JsonObject arguments, long started) {
        if (!player.hasPermission("neighborhood.agent.build")) {
            return ToolResult.fail("I can't build here. Try: ask a grown-up for help.", elapsedMs(started));
        }
        String mode = optionalString(arguments, "mode");
        if (mode == null || mode.isBlank()) {
            mode = "fill";
        }
        mode = mode.toLowerCase(Locale.ROOT);
        if (!Set.of("fill", "replace", "clear").contains(mode)) {
            return ToolResult.fail("I couldn't understand that floor request.", elapsedMs(started));
        }
        String requestedMaterial = optionalString(arguments, "material");
        GazeHit gaze = GazeSensor.capture(player);
        // Fill needs an open air plane; replace/clear prefer a solid walkable floor.
        boolean preferSolid = !"fill".equals(mode);
        FloorFacet floor = GeometrySensor.findFloor(player, gaze, preferSolid);
        if (floor == null) {
            return ToolResult.fail(
                    "I couldn't find a floor to finish. Try: stand in a room and look down.",
                    elapsedMs(started)
            );
        }
        Material material = null;
        if (!"clear".equals(mode)) {
            material = resolveFloorMaterial(player, requestedMaterial);
            if (material == null) {
                return ToolResult.fail(
                        "Hold the block you want, or say the material. Try: finish this floor with oak planks",
                        elapsedMs(started)
                );
            }
            if (RESTRICTED_ITEMS.contains(material)) {
                return ToolResult.fail("I can’t use that block safely.", elapsedMs(started));
            }
        }
        World world = player.getWorld();
        List<Block> changes = collectFloorChanges(world, floor, mode, material);
        if (changes.isEmpty()) {
            if ("clear".equals(mode)) {
                return ToolResult.ok(
                        "That floor is already clear.",
                        true,
                        elapsedMs(started)
                );
            }
            if ("replace".equals(mode)) {
                return ToolResult.ok(
                        "That floor is already " + material.getKey().getKey().replace('_', ' ') + ".",
                        true,
                        elapsedMs(started)
                );
            }
            return ToolResult.ok(
                    "That " + floor.width() + "×" + floor.depth() + " floor is already filled in.",
                    true,
                    elapsedMs(started)
            );
        }
        if (changes.size() > MAX_FLOOR_CELLS) {
            return ToolResult.fail(
                    "That floor is too big to finish safely in one go.",
                    elapsedMs(started)
            );
        }
        Material policyMaterial = "clear".equals(mode) ? Material.AIR : material;
        String denied = buildPolicy.denyReason(
                player,
                changes.stream().map(Block::getLocation).toList(),
                policyMaterial
        );
        if (denied != null) {
            return ToolResult.fail(denied, elapsedMs(started));
        }
        Material target = "clear".equals(mode) ? Material.AIR : material;
        Runnable undo = BoundedFaweEdit.apply(
                world, player.getUniqueId(), changes, target
        );
        boolean verified = changes.stream().allMatch(block -> block.getType() == target);
        if (!verified) {
            undo.run();
            return ToolResult.fail(
                    "I couldn't finish that floor exactly, so I put things back.",
                    elapsedMs(started)
            );
        }
        rememberUndo(player, undo);
        if ("clear".equals(mode)) {
            return ToolResult.ok(
                    "Cleared that floor (" + floor.width() + " by " + floor.depth()
                            + "). Say “undo that” if you don’t like it.",
                    true,
                    elapsedMs(started)
            );
        }
        String readable = material.getKey().getKey().replace('_', ' ');
        String verb = "replace".equals(mode) ? "Changed your floor to " : "Finished your ";
        String noun = "replace".equals(mode) ? "" : " floor";
        return ToolResult.ok(
                verb + readable + noun + " (" + floor.width() + " by "
                        + floor.depth() + "). Say “undo that” if you don’t like it.",
                true,
                elapsedMs(started)
        );
    }

    private List<Block> collectFloorChanges(
            World world,
            FloorFacet floor,
            String mode,
            Material material
    ) {
        List<Block> changes = new ArrayList<>();
        for (int x = floor.minX(); x <= floor.maxX(); x++) {
            for (int z = floor.minZ(); z <= floor.maxZ(); z++) {
                Block block = world.getBlockAt(x, floor.y(), z);
                if (isPerimeterWallLike(world, floor, x, z, block)) {
                    continue;
                }
                if ("fill".equals(mode)) {
                    if (block.getType().isAir()) {
                        changes.add(block);
                    }
                } else if ("replace".equals(mode)) {
                    if (!block.getType().isAir()
                            && block.getType() != material
                            && !RESTRICTED_ITEMS.contains(block.getType())) {
                        changes.add(block);
                    }
                } else if ("clear".equals(mode)) {
                    if (!block.getType().isAir()
                            && !RESTRICTED_ITEMS.contains(block.getType())) {
                        changes.add(block);
                    }
                }
            }
        }
        return changes;
    }

    private static boolean isPerimeterWallLike(
            World world,
            FloorFacet floor,
            int x,
            int z,
            Block block
    ) {
        if (block.getType().isAir()) {
            return false;
        }
        // Wall columns continue upward; true floor cells have air above.
        return isSolid(world.getBlockAt(x, floor.y() + 1, z));
    }

    private static boolean isSolid(Block block) {
        return block.getType().isSolid() && !block.isPassable();
    }

    private Material resolveFloorMaterial(Player player, String requested) {
        if (requested != null && !requested.isBlank()) {
            Material material = Material.matchMaterial(requested);
            if (material != null && material.isBlock() && !material.isAir()) {
                return material;
            }
        }
        ItemStack held = player.getInventory().getItemInMainHand();
        if (held != null && held.getType().isBlock() && !held.getType().isAir()) {
            return held.getType();
        }
        return null;
    }

    private Material resolveWallMaterial(Player player, String requested, OpeningFacet opening) {
        if (requested != null && !requested.isBlank()) {
            Material material = Material.matchMaterial(requested);
            if (material != null && material.isBlock() && !material.isAir()) {
                return material;
            }
        }
        ItemStack held = player.getInventory().getItemInMainHand();
        if (held != null && held.getType().isBlock() && !held.getType().isAir()) {
            return held.getType();
        }
        if (opening != null && opening.suggestedMaterial() != null) {
            Material material = Material.matchMaterial(opening.suggestedMaterial());
            if (material != null && material.isBlock() && !material.isAir()) {
                return material;
            }
        }
        return null;
    }

    private static Integer optionalInt(JsonObject arguments, String key, int min, int max) {
        if (!arguments.has(key) || arguments.get(key).isJsonNull()) {
            return null;
        }
        int value = arguments.get(key).getAsInt();
        if (value < min || value > max) {
            return null;
        }
        return value;
    }

    private static String optionalString(JsonObject arguments, String key) {
        if (!arguments.has(key) || arguments.get(key).isJsonNull()) {
            return null;
        }
        return arguments.get(key).getAsString();
    }

    private WallCandidate findWallCandidate(Player player, Block start, Material material) {
        double facingX = player.getLocation().getDirection().getX();
        double facingZ = player.getLocation().getDirection().getZ();
        List<int[]> directions = new ArrayList<>(4);
        if (Math.abs(facingX) >= Math.abs(facingZ)) {
            directions.add(new int[]{facingX >= 0 ? 1 : -1, 0});
            directions.add(new int[]{facingX >= 0 ? -1 : 1, 0});
            directions.add(new int[]{0, facingZ >= 0 ? 1 : -1});
            directions.add(new int[]{0, facingZ >= 0 ? -1 : 1});
        } else {
            directions.add(new int[]{0, facingZ >= 0 ? 1 : -1});
            directions.add(new int[]{0, facingZ >= 0 ? -1 : 1});
            directions.add(new int[]{facingX >= 0 ? 1 : -1, 0});
            directions.add(new int[]{facingX >= 0 ? -1 : 1, 0});
        }
        for (int[] direction : directions) {
            WallCandidate candidate = scanWallDirection(start, material, direction[0], direction[1]);
            if (candidate != null) {
                return candidate;
            }
        }
        return null;
    }

    private WallCandidate scanWallDirection(Block start, Material material, int stepX, int stepZ) {
        // Skip any contiguous same-material run attached to the looked-at end, then require
        // an air gap before the far matching post. That keeps "two posts" from latching onto
        // a neighboring floor/path of the same block type.
        int maxScan = PerceptionBudget.MAX_OPENING_LENGTH;
        int distance = 1;
        while (distance <= maxScan) {
            Block block = start.getRelative(stepX * distance, 0, stepZ * distance);
            if (block.getType() != material) {
                break;
            }
            distance++;
        }
        if (distance > maxScan) {
            return null;
        }
        boolean sawAirGap = false;
        for (; distance <= maxScan; distance++) {
            Block block = start.getRelative(stepX * distance, 0, stepZ * distance);
            if (block.getType().isAir()) {
                sawAirGap = true;
                continue;
            }
            if (block.getType() == material && sawAirGap && distance >= 2) {
                return new WallCandidate(block, distance);
            }
            return null;
        }
        return null;
    }

    private void rememberUndo(Player player, Runnable rollback) {
        undo.put(
                player.getUniqueId(),
                new UndoAction(System.currentTimeMillis(), rollback)
        );
    }

    private static String requiredString(JsonObject arguments, String key) {
        if (!arguments.has(key) || !arguments.get(key).isJsonPrimitive()) {
            throw new IllegalArgumentException("missing " + key);
        }
        return arguments.get(key).getAsString();
    }

    private static int requiredInt(JsonObject arguments, String key, int min, int max) {
        if (!arguments.has(key) || !arguments.get(key).isJsonPrimitive()) {
            throw new IllegalArgumentException("missing " + key);
        }
        int value = arguments.get(key).getAsInt();
        if (value < min || value > max) {
            throw new IllegalArgumentException("invalid " + key);
        }
        return value;
    }

    private static int elapsedMs(long started) {
        return (int) ((System.nanoTime() - started) / 1_000_000L);
    }

    record ToolResult(
            boolean ok,
            boolean executed,
            boolean verified,
            String message,
            int executionMs
    ) {
        static ToolResult ok(String message, boolean verified, int executionMs) {
            return new ToolResult(verified, true, verified, message, executionMs);
        }

        static ToolResult fail(String message, int executionMs) {
            return new ToolResult(false, false, false, message, executionMs);
        }
    }

    private record UndoAction(long createdAtMs, Runnable rollback) {
    }

    private record WallCandidate(Block end, int distance) {
    }

}
