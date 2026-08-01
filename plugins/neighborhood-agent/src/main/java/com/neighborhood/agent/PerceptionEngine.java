package com.neighborhood.agent;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

final class PerceptionEngine {
    private final NeighborhoodAgentPlugin plugin;
    private final PerceptionPolicy policy;
    private final AtomicInteger activeServer = new AtomicInteger();
    private final Map<UUID, AtomicInteger> activePlayers = new ConcurrentHashMap<>();
    private final AtomicInteger queued = new AtomicInteger();

    PerceptionEngine(NeighborhoodAgentPlugin plugin, BuildPolicy buildPolicy) {
        this.plugin = plugin;
        this.policy = new PerceptionPolicy(buildPolicy);
    }

    JsonObject captureFast(Player player) {
        long started = System.nanoTime();
        GazeHit gaze = GazeSensor.capture(player);
        ItemStack heldStack = player.getInventory().getItemInMainHand();
        boolean heldBlock = heldStack != null
                && !heldStack.getType().isAir()
                && heldStack.getType().isBlock();
        PolicySnapshot policySnapshot = policy.probe(player, gaze.block());
        String fingerprint = SceneFingerprint.fast(
                player,
                gaze.block(),
                gaze.face(),
                heldStack
        );
        Location loc = player.getLocation();
        JsonObject pose = new JsonObject();
        pose.addProperty("x", loc.getX());
        pose.addProperty("y", loc.getY());
        pose.addProperty("z", loc.getZ());
        pose.addProperty("yaw", loc.getYaw());
        pose.addProperty("pitch", loc.getPitch());

        JsonObject gazeJson = new JsonObject();
        gazeJson.addProperty("hit", gaze.hit());
        gazeJson.addProperty("distance_blocks", gaze.distance());
        if (gaze.hit() && gaze.block() != null) {
            gazeJson.addProperty("material", materialKey(gaze.block().getType()));
            if (gaze.face() != null) {
                gazeJson.addProperty("face", gaze.face().name().toLowerCase());
            }
            JsonObject pos = new JsonObject();
            pos.addProperty("x", gaze.block().getX());
            pos.addProperty("y", gaze.block().getY());
            pos.addProperty("z", gaze.block().getZ());
            gazeJson.add("pos", pos);
        } else {
            gazeJson.add("material", null);
            gazeJson.add("face", null);
            gazeJson.add("pos", null);
        }

        JsonObject held = new JsonObject();
        held.addProperty("is_block", heldBlock);
        if (heldBlock) {
            held.addProperty("material", materialKey(heldStack.getType()));
        } else {
            held.add("material", null);
        }

        JsonObject policyJson = policyJson(policySnapshot);
        int captureMs = (int) ((System.nanoTime() - started) / 1_000_000L);

        JsonObject observation = new JsonObject();
        observation.addProperty("schema_version", "1.0");
        observation.addProperty("observation_id", UUID.randomUUID().toString());
        observation.addProperty("captured_at_ms", System.currentTimeMillis());
        observation.addProperty("world", player.getWorld().getKey().toString());
        observation.add("pose", pose);
        observation.add("gaze", gazeJson);
        observation.add("held", held);
        observation.add("policy", policyJson);
        observation.addProperty("fingerprint", fingerprint);
        observation.addProperty("capture_ms", captureMs);
        return observation;
    }

    CompletableFuture<JsonObject> inspectAsync(Player player, String purpose, String parentObservationId) {
        UUID playerId = player.getUniqueId();
        AtomicInteger playerActive = activePlayers.computeIfAbsent(playerId, ignored -> new AtomicInteger());
        if (playerActive.get() >= PerceptionBudget.MAX_ACTIVE_PER_PLAYER
                || activeServer.get() >= PerceptionBudget.MAX_ACTIVE_SERVER
                || queued.get() >= PerceptionBudget.MAX_QUEUE) {
            return CompletableFuture.completedFuture(busyScene(parentObservationId, purpose));
        }
        queued.incrementAndGet();
        CompletableFuture<JsonObject> future = new CompletableFuture<>();
        plugin.getServer().getScheduler().runTask(plugin, () -> {
            queued.decrementAndGet();
            if (!player.isOnline()) {
                future.complete(busyScene(parentObservationId, purpose));
                return;
            }
            playerActive.incrementAndGet();
            activeServer.incrementAndGet();
            try {
                future.complete(inspectNow(player, purpose, parentObservationId));
            } catch (RuntimeException error) {
                plugin.getLogger().warning("Perception inspect failed: " + error.getMessage());
                future.complete(busyScene(parentObservationId, purpose));
            } finally {
                playerActive.decrementAndGet();
                activeServer.decrementAndGet();
            }
        });
        return future;
    }

    GeometryResult inspectGeometry(Player player, String purpose) {
        GazeHit gaze = GazeSensor.capture(player);
        ItemStack held = player.getInventory().getItemInMainHand();
        String heldMaterial = held != null && held.getType().isBlock() && !held.getType().isAir()
                ? materialKey(held.getType())
                : null;
        return GeometrySensor.inspect(player, gaze, purpose, heldMaterial);
    }

    boolean isPoseStale(Player player, JsonObject fastObservation) {
        if (fastObservation == null || !fastObservation.has("pose")) {
            return true;
        }
        long captured = fastObservation.has("captured_at_ms")
                ? fastObservation.get("captured_at_ms").getAsLong()
                : 0L;
        if (System.currentTimeMillis() - captured > PerceptionBudget.OBSERVATION_TTL_MS) {
            return true;
        }
        JsonObject pose = fastObservation.getAsJsonObject("pose");
        return SceneFingerprint.poseStale(
                player,
                pose.get("x").getAsDouble(),
                pose.get("y").getAsDouble(),
                pose.get("z").getAsDouble(),
                pose.get("yaw").getAsFloat(),
                pose.get("pitch").getAsFloat()
        );
    }

    int queueDepth() {
        return queued.get();
    }

    int activeCount() {
        return activeServer.get();
    }

    private JsonObject inspectNow(Player player, String purpose, String parentObservationId) {
        GazeHit gaze = GazeSensor.capture(player);
        ItemStack held = player.getInventory().getItemInMainHand();
        String heldMaterial = held != null && held.getType().isBlock() && !held.getType().isAir()
                ? materialKey(held.getType())
                : null;
        GeometryResult geometry = GeometrySensor.inspect(player, gaze, purpose, heldMaterial);
        NearbyFacet nearby = NearbySensor.capture(player, gaze);
        PolicySnapshot policySnapshot = policy.probe(player, gaze.block());

        JsonObject scene = new JsonObject();
        scene.addProperty("schema_version", "1.0");
        scene.addProperty("observation_id", UUID.randomUUID().toString());
        scene.addProperty("parent_observation_id", parentObservationId == null
                ? UUID.randomUUID().toString()
                : parentObservationId);
        scene.addProperty("captured_at_ms", System.currentTimeMillis());
        scene.addProperty("purpose", purpose);
        scene.addProperty("fingerprint", geometry.fingerprint());
        scene.addProperty("confidence", geometry.confidence());

        JsonObject budget = new JsonObject();
        budget.addProperty("cells_sampled", geometry.budget().cellsSampled());
        budget.addProperty("elapsed_ms", geometry.budget().elapsedMs());
        budget.addProperty("truncated", geometry.budget().truncated());
        budget.addProperty("bytes", 0);
        scene.add("budget", budget);

        if (geometry.surface() != null) {
            scene.add("surface", surfaceJson(geometry.surface()));
        } else {
            scene.add("surface", null);
        }

        JsonArray openings = new JsonArray();
        for (OpeningFacet opening : geometry.openings()) {
            openings.add(openingJson(opening));
        }
        scene.add("openings", openings);

        if (geometry.clearance() != null) {
            scene.add("clearance", clearanceJson(geometry.clearance()));
        } else {
            scene.add("clearance", null);
        }

        JsonArray palette = new JsonArray();
        for (PaletteEntry entry : geometry.palette()) {
            JsonObject item = new JsonObject();
            item.addProperty("material", entry.material());
            item.addProperty("count", entry.count());
            palette.add(item);
        }
        scene.add("palette", palette);

        JsonObject nearbyJson = new JsonObject();
        nearbyJson.addProperty("friendly_count", nearby.friendlyCount());
        nearbyJson.addProperty("hostile_count", nearby.hostileCount());
        if (nearby.interactable() == null) {
            nearbyJson.add("interactable", null);
        } else {
            nearbyJson.addProperty("interactable", nearby.interactable());
        }
        scene.add("nearby", nearbyJson);
        scene.add("policy", policyJson(policySnapshot));
        budget.addProperty("bytes", scene.toString().length());
        return scene;
    }

    private JsonObject busyScene(String parentObservationId, String purpose) {
        JsonObject scene = new JsonObject();
        scene.addProperty("schema_version", "1.0");
        scene.addProperty("observation_id", UUID.randomUUID().toString());
        scene.addProperty("parent_observation_id", parentObservationId == null
                ? UUID.randomUUID().toString()
                : parentObservationId);
        scene.addProperty("captured_at_ms", System.currentTimeMillis());
        scene.addProperty("purpose", purpose);
        // Keep fingerprint schema-valid (min 8 chars) so companion can parse busy scenes.
        scene.addProperty("fingerprint", "busy000000000000");
        scene.addProperty("confidence", "none");
        JsonObject budget = new JsonObject();
        budget.addProperty("cells_sampled", 0);
        budget.addProperty("elapsed_ms", 0);
        budget.addProperty("truncated", true);
        budget.addProperty("bytes", 0);
        scene.add("budget", budget);
        scene.add("surface", null);
        scene.add("openings", new JsonArray());
        scene.add("clearance", null);
        scene.add("palette", new JsonArray());
        scene.add("nearby", null);
        scene.add("policy", policyJson(PolicySnapshot.allow()));
        return scene;
    }

    private static JsonObject policyJson(PolicySnapshot snapshot) {
        JsonObject policyJson = new JsonObject();
        policyJson.addProperty("can_build_at_target", snapshot.canBuildAtTarget());
        policyJson.addProperty("in_claim", snapshot.inClaim());
        policyJson.addProperty("has_build_permission", snapshot.hasBuildPermission());
        if (snapshot.denyReason() == null) {
            policyJson.add("deny_reason", null);
        } else {
            policyJson.addProperty("deny_reason", snapshot.denyReason());
        }
        return policyJson;
    }

    private static JsonObject openingJson(OpeningFacet opening) {
        JsonObject json = new JsonObject();
        json.addProperty("axis", opening.axis());
        json.addProperty("min_x", opening.minX());
        json.addProperty("max_x", opening.maxX());
        json.addProperty("min_y", opening.minY());
        json.addProperty("max_y", opening.maxY());
        json.addProperty("min_z", opening.minZ());
        json.addProperty("max_z", opening.maxZ());
        json.addProperty("length", opening.length());
        json.addProperty("height", opening.height());
        json.addProperty("air_cells", opening.airCells());
        json.addProperty("end_a_material", opening.endAMaterial());
        json.addProperty("end_b_material", opening.endBMaterial());
        json.addProperty("suggested_material", opening.suggestedMaterial());
        json.addProperty("confidence", opening.confidence());
        return json;
    }

    private static JsonObject surfaceJson(SurfaceFacet surface) {
        JsonObject json = new JsonObject();
        json.addProperty("axis", surface.axis());
        json.addProperty("normal", surface.normal());
        json.addProperty("min_x", surface.minX());
        json.addProperty("max_x", surface.maxX());
        json.addProperty("min_y", surface.minY());
        json.addProperty("max_y", surface.maxY());
        json.addProperty("min_z", surface.minZ());
        json.addProperty("max_z", surface.maxZ());
        json.addProperty("width", surface.width());
        json.addProperty("height", surface.height());
        json.addProperty("material", surface.material());
        json.addProperty("confidence", surface.confidence());
        return json;
    }

    private static JsonObject clearanceJson(ClearanceFacet clearance) {
        JsonObject json = new JsonObject();
        json.addProperty("min_x", clearance.minX());
        json.addProperty("max_x", clearance.maxX());
        json.addProperty("min_y", clearance.minY());
        json.addProperty("max_y", clearance.maxY());
        json.addProperty("min_z", clearance.minZ());
        json.addProperty("max_z", clearance.maxZ());
        json.addProperty("width", clearance.width());
        json.addProperty("height", clearance.height());
        json.addProperty("depth", clearance.depth());
        json.addProperty("air_cells", clearance.airCells());
        json.addProperty("confidence", clearance.confidence());
        return json;
    }

    private static String materialKey(Material material) {
        return material.getKey().getKey();
    }
}
