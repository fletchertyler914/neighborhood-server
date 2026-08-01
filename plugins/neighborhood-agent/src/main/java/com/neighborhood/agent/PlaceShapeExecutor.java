package com.neighborhood.agent;

import com.google.gson.JsonObject;
import com.neighborhood.agent.NativeToolRegistry.ToolResult;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.util.Vector;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.function.BiConsumer;

/**
 * Player-relative parametric shapes for the NL world editor.
 */
final class PlaceShapeExecutor {
    private static final int MAX_WALL_CELLS = 1_536;
    private static final int MAX_PLATFORM_CELLS = 1_024;
    private static final int MAX_OUTLINE_CELLS = 4_000;
    private static final int MAX_SOLID_CELLS = 4_096;
    private static final Set<Material> RESTRICTED = Set.of(
            Material.COMMAND_BLOCK,
            Material.CHAIN_COMMAND_BLOCK,
            Material.REPEATING_COMMAND_BLOCK,
            Material.STRUCTURE_BLOCK,
            Material.JIGSAW,
            Material.DEBUG_STICK,
            Material.BARRIER,
            Material.BEDROCK,
            Material.TNT,
            Material.LAVA_BUCKET
    );

    private final BuildPolicy buildPolicy;
    private final BiConsumer<Player, Runnable> rememberUndo;
    private final NativeToolRegistry.WallFinisher wallFinisher;

    PlaceShapeExecutor(
            BuildPolicy buildPolicy,
            PerceptionEngine perception,
            BiConsumer<Player, Runnable> rememberUndo,
            NativeToolRegistry.WallFinisher wallFinisher
    ) {
        this.buildPolicy = buildPolicy;
        this.rememberUndo = rememberUndo;
        this.wallFinisher = wallFinisher;
    }

    ToolResult execute(Player player, JsonObject arguments, long started) {
        if (!player.hasPermission("neighborhood.agent.build")) {
            return ToolResult.fail("I can't build here. Try: ask a grown-up for help.", elapsed(started));
        }
        String kind = requiredString(arguments, "kind").toLowerCase(Locale.ROOT);
        Material material = resolveMaterial(player, optionalString(arguments, "material"));
        if (material == null) {
            return ToolResult.fail(
                    "Hold the block you want, or say the material. Try: 5x5 oak platform",
                    elapsed(started)
            );
        }
        if (RESTRICTED.contains(material) || !material.isBlock() || material.isAir()) {
            return ToolResult.fail("I can’t use that block safely.", elapsed(started));
        }

        // Sized wall asks prefer finish_wall (geometry + legacy post-pair) whenever
        // an opening is visible. Only free-stand place when no opening/posts exist.
        if ("wall".equals(kind)) {
            JsonObject finishArgs = new JsonObject();
            if (arguments.has("height")) {
                finishArgs.addProperty("height", arguments.get("height").getAsInt());
            }
            if (arguments.has("material")) {
                finishArgs.addProperty("material", arguments.get("material").getAsString());
            }
            ToolResult finished = wallFinisher.finish(player, finishArgs, started);
            if (finished.ok()) {
                return finished;
            }
            String msg = finished.message() == null
                    ? ""
                    : finished.message().toLowerCase(Locale.ROOT);
            // Fall through only when perception found nothing to finish.
            if (!msg.contains("couldn't find")
                    && !msg.contains("couldn’t find")
                    && !msg.contains("look at a corner")) {
                return finished;
            }
        }

        return switch (kind) {
            case "wall" -> placeWall(player, arguments, material, started);
            case "platform" -> placePlatform(player, arguments, material, started);
            case "box_shell" -> placeBox(player, arguments, material, started, false);
            case "solid_box" -> placeBox(player, arguments, material, started, true);
            case "cylinder" -> placeCylinder(player, arguments, material, started);
            default -> ToolResult.fail("I don't know that shape.", elapsed(started));
        };
    }

    private ToolResult placeWall(Player player, JsonObject args, Material material, long started) {
        int length = clamp(optionalInt(args, "length", 8), 2, 48);
        int height = clamp(optionalInt(args, "height", 4), 1, 32);
        if (length * height > MAX_WALL_CELLS) {
            return ToolResult.fail("That wall is too big. Try a smaller size.", elapsed(started));
        }
        Vector forward = horizontalForward(player);
        // Right-hand horizontal: up × forward → (fz, 0, -fx).
        Vector right = new Vector(forward.getZ(), 0, -forward.getX());
        Location origin = player.getLocation().getBlock().getLocation().add(forward.clone().multiply(3));
        // Center wall on facing axis.
        int start = -(length / 2);
        World world = player.getWorld();
        List<Block> blocks = new ArrayList<>();
        for (int i = 0; i < length; i++) {
            Vector offset = right.clone().multiply(start + i);
            int bx = origin.getBlockX() + offset.getBlockX();
            int bz = origin.getBlockZ() + offset.getBlockZ();
            int baseY = supportY(world, bx, origin.getBlockY(), bz);
            for (int y = 0; y < height; y++) {
                blocks.add(world.getBlockAt(bx, baseY + 1 + y, bz));
            }
        }
        return apply(player, blocks, material, started,
                "Built a " + readable(material) + " wall (" + length + " long, " + height + " tall).");
    }

    private ToolResult placePlatform(Player player, JsonObject args, Material material, long started) {
        int width = clamp(optionalInt(args, "width", 5), 1, 32);
        int depth = clamp(optionalInt(args, "depth", width), 1, 32);
        if (width * depth > MAX_PLATFORM_CELLS) {
            return ToolResult.fail("That platform is too big. Try up to 32×32.", elapsed(started));
        }
        Vector forward = horizontalForward(player);
        Location feet = player.getLocation().getBlock().getLocation();
        int originX;
        int originZ;
        if (Math.abs(forward.getX()) >= Math.abs(forward.getZ())) {
            originZ = feet.getBlockZ() - (depth / 2);
            originX = feet.getBlockX() + (forward.getX() >= 0 ? 2 : -width - 1);
        } else {
            originX = feet.getBlockX() - (width / 2);
            originZ = feet.getBlockZ() + (forward.getZ() >= 0 ? 2 : -depth - 1);
        }
        World world = player.getWorld();
        int y = supportY(world, feet.getBlockX(), feet.getBlockY(), feet.getBlockZ());
        List<Block> blocks = new ArrayList<>();
        for (int x = 0; x < width; x++) {
            for (int z = 0; z < depth; z++) {
                blocks.add(world.getBlockAt(originX + x, y, originZ + z));
            }
        }
        return apply(player, blocks, material, started,
                "Built a " + width + "×" + depth + " " + readable(material) + " platform.");
    }

    private ToolResult placeBox(
            Player player,
            JsonObject args,
            Material material,
            long started,
            boolean solid
    ) {
        int width = clamp(optionalInt(args, "width", 5), 3, 24);
        int depth = clamp(optionalInt(args, "depth", width), 3, 24);
        int height = clamp(optionalInt(args, "height", 4), 2, 24);
        boolean roof = !args.has("roof") || args.get("roof").getAsBoolean();
        Vector forward = horizontalForward(player);
        Location feet = player.getLocation().getBlock().getLocation();
        int minX;
        int minZ;
        if (Math.abs(forward.getX()) >= Math.abs(forward.getZ())) {
            minX = feet.getBlockX() + (forward.getX() >= 0 ? 2 : -width - 1);
            minZ = feet.getBlockZ() - (depth / 2);
        } else {
            minX = feet.getBlockX() - (width / 2);
            minZ = feet.getBlockZ() + (forward.getZ() >= 0 ? 2 : -depth - 1);
        }
        World world = player.getWorld();
        int minY = supportY(world, feet.getBlockX(), feet.getBlockY(), feet.getBlockZ()) + 1;
        int maxX = minX + width - 1;
        int maxZ = minZ + depth - 1;
        int maxY = minY + height - 1;
        List<Block> blocks = new ArrayList<>();
        for (int x = minX; x <= maxX; x++) {
            for (int y = minY; y <= maxY; y++) {
                for (int z = minZ; z <= maxZ; z++) {
                    boolean wall = x == minX || x == maxX || z == minZ || z == maxZ;
                    boolean isRoof = roof && y == maxY;
                    if (solid || wall || isRoof) {
                        blocks.add(world.getBlockAt(x, y, z));
                    }
                }
            }
        }
        int cap = solid ? MAX_SOLID_CELLS : MAX_OUTLINE_CELLS;
        if (blocks.size() > cap) {
            return ToolResult.fail("That box is too big. Try a smaller size.", elapsed(started));
        }
        String label = solid ? "solid box" : "box";
        return apply(player, blocks, material, started,
                "Built a " + width + "×" + depth + "×" + height + " " + readable(material) + " " + label + ".");
    }

    private ToolResult placeCylinder(Player player, JsonObject args, Material material, long started) {
        int diameter = clamp(optionalInt(args, "width", 6), 2, 32);
        int height = clamp(optionalInt(args, "height", 8), 1, 32);
        int radius = Math.max(1, diameter / 2);
        Vector forward = horizontalForward(player);
        Location feet = player.getLocation().getBlock().getLocation();
        int cx = feet.getBlockX() + forward.getBlockX() * (radius + 2);
        int cz = feet.getBlockZ() + forward.getBlockZ() * (radius + 2);
        World world = player.getWorld();
        int baseY = supportY(world, feet.getBlockX(), feet.getBlockY(), feet.getBlockZ()) + 1;
        List<Block> blocks = new ArrayList<>();
        for (int y = 0; y < height; y++) {
            for (int x = -radius; x <= radius; x++) {
                for (int z = -radius; z <= radius; z++) {
                    if (x * x + z * z <= radius * radius) {
                        blocks.add(world.getBlockAt(cx + x, baseY + y, cz + z));
                    }
                }
            }
        }
        if (blocks.size() > MAX_SOLID_CELLS) {
            return ToolResult.fail("That cylinder is too big. Try a smaller size.", elapsed(started));
        }
        return apply(player, blocks, material, started,
                "Built a " + readable(material) + " cylinder (" + height + " tall).");
    }

    private ToolResult apply(
            Player player,
            List<Block> blocks,
            Material material,
            long started,
            String okMessage
    ) {
        if (blocks.isEmpty()) {
            return ToolResult.fail("I couldn't find a clear spot for that.", elapsed(started));
        }
        // Refuse overlapping the player's column.
        int px = player.getLocation().getBlockX();
        int pz = player.getLocation().getBlockZ();
        int py = player.getLocation().getBlockY();
        for (Block block : blocks) {
            if (block.getX() == px && block.getZ() == pz
                    && block.getY() >= py && block.getY() <= py + 1) {
                return ToolResult.fail(
                        "You're in the way — step back and try again.",
                        elapsed(started)
                );
            }
        }
        List<Location> locations = blocks.stream().map(Block::getLocation).toList();
        String denied = buildPolicy.denyReason(player, locations, material);
        if (denied != null) {
            return ToolResult.fail(denied, elapsed(started));
        }
        Runnable undo = BoundedFaweEdit.apply(
                player.getWorld(), player.getUniqueId(), blocks, material
        );
        boolean verified = blocks.stream().allMatch(block -> block.getType() == material);
        if (!verified) {
            undo.run();
            return ToolResult.fail("I couldn't place that exactly, so I put things back.", elapsed(started));
        }
        rememberUndo.accept(player, undo);
        return ToolResult.ok(
                okMessage + " Say “undo that” if you don’t like it.",
                true,
                elapsed(started)
        );
    }

    private static Material resolveMaterial(Player player, String requested) {
        if (requested != null && !requested.isBlank()) {
            String key = requested.toLowerCase(Locale.ROOT).replace("minecraft:", "");
            Material material = Material.matchMaterial(key);
            if (material != null && material.isBlock() && !material.isAir()) {
                return material;
            }
            // Explicit material was requested but is not a placeable block —
            // do not silently fall back to the held item (that caused dirt
            // platforms when routing sent oak_platform / stone_box).
            return null;
        }
        var hand = player.getInventory().getItemInMainHand();
        if (hand != null && hand.getType().isBlock() && !hand.getType().isAir()) {
            return hand.getType();
        }
        return null;
    }

    private static Vector horizontalForward(Player player) {
        Vector direction = player.getLocation().getDirection();
        direction.setY(0);
        if (direction.lengthSquared() < 1.0e-6) {
            return new Vector(0, 0, 1);
        }
        direction.normalize();
        // Snap to cardinal for clean builds.
        if (Math.abs(direction.getX()) >= Math.abs(direction.getZ())) {
            return new Vector(direction.getX() >= 0 ? 1 : -1, 0, 0);
        }
        return new Vector(0, 0, direction.getZ() >= 0 ? 1 : -1);
    }

    private static int supportY(World world, int x, int nearY, int z) {
        int y = Math.min(nearY + 2, world.getMaxHeight() - 2);
        int min = world.getMinHeight();
        while (y > min) {
            Block block = world.getBlockAt(x, y, z);
            if (!block.getType().isAir() && block.getType().isSolid()) {
                return y;
            }
            y--;
        }
        return Math.max(min, nearY - 1);
    }

    private static String readable(Material material) {
        return material.getKey().getKey().replace('_', ' ');
    }

    private static int clamp(int value, int min, int max) {
        return Math.max(min, Math.min(max, value));
    }

    private static int optionalInt(JsonObject arguments, String key, int defaultValue) {
        if (!arguments.has(key) || arguments.get(key).isJsonNull()) {
            return defaultValue;
        }
        return arguments.get(key).getAsInt();
    }

    private static String optionalString(JsonObject arguments, String key) {
        if (!arguments.has(key) || arguments.get(key).isJsonNull()) {
            return null;
        }
        return arguments.get(key).getAsString();
    }

    private static String requiredString(JsonObject arguments, String key) {
        String value = optionalString(arguments, key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(key);
        }
        return value;
    }

    private static int elapsed(long started) {
        return (int) ((System.nanoTime() - started) / 1_000_000L);
    }
}
