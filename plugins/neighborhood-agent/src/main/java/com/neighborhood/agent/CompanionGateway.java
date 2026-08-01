package com.neighborhood.agent;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.bukkit.Bukkit;
import org.bukkit.GameMode;
import org.bukkit.entity.Player;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

public final class CompanionGateway implements AutoCloseable, WebSocket.Listener {
    private static final String PROTOCOL = "1.0";
    private static final Gson GSON = new Gson();

    private final NeighborhoodAgentPlugin plugin;
    private final HttpClient http;
    private final NativeToolRegistry tools;
    private final IdempotencyJournal journal;
    private final PerceptionEngine perception;
    private final AtomicLong sequence = new AtomicLong();
    private final AtomicBoolean closing = new AtomicBoolean(false);
    private final Map<String, PendingJob> jobs = new ConcurrentHashMap<>();
    private final StringBuilder incoming = new StringBuilder();

    private volatile WebSocket socket;
    private volatile boolean ready;

    public CompanionGateway(NeighborhoodAgentPlugin plugin) {
        this.plugin = plugin;
        BuildPolicy buildPolicy = new BuildPolicy(plugin);
        this.perception = new PerceptionEngine(plugin, buildPolicy);
        this.tools = new NativeToolRegistry(plugin, perception, buildPolicy);
        this.journal = new IdempotencyJournal(plugin);
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();
    }

    PerceptionEngine perception() {
        return perception;
    }

    public void start() {
        connect();
        plugin.getServer().getScheduler().runTaskTimerAsynchronously(
                plugin,
                this::sendHeartbeat,
                100L,
                100L
        );
    }

    public String getGatewayUrl() {
        return plugin.getConfig().getString(
                "gateway-url",
                "ws://mc-agent:8787/v1/gateway"
        );
    }

    public boolean isReady() {
        return ready && socket != null;
    }

    private String getApiToken() {
        String configured = plugin.getConfig().getString("api-token", "env:AGENT_API_TOKEN");
        if (configured != null && configured.startsWith("env:")) {
            String value = System.getenv(configured.substring("env:".length()));
            return value == null ? "" : value.trim();
        }
        return configured == null ? "" : configured.trim();
    }

    private void connect() {
        if (closing.get()) {
            return;
        }
        String token = getApiToken();
        if (token.isBlank()) {
            plugin.getLogger().severe("AGENT_API_TOKEN is missing; /agent is disabled");
            scheduleReconnect();
            return;
        }
        try {
            http.newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(5))
                    .header("Authorization", "Bearer " + token)
                    .buildAsync(URI.create(getGatewayUrl()), this)
                    .exceptionally(error -> {
                        plugin.getLogger().warning("Companion connection failed: " + rootMessage(error));
                        scheduleReconnect();
                        return null;
                    });
        } catch (RuntimeException error) {
            plugin.getLogger().warning("Invalid companion gateway configuration: " + error.getMessage());
            scheduleReconnect();
        }
    }

    private void scheduleReconnect() {
        if (closing.get()) {
            return;
        }
        plugin.getServer().getScheduler().runTaskLaterAsynchronously(
                plugin,
                this::connect,
                60L
        );
    }

    public CompletableFuture<JobResult> submitJob(JobPayload payload) {
        if (!isReady()) {
            return CompletableFuture.completedFuture(
                    JobResult.fail("Your sidekick is waking up. Try again in a moment.")
            );
        }
        String jobId = UUID.randomUUID().toString();
        String traceId = UUID.randomUUID().toString();
        CompletableFuture<JobResult> future = new CompletableFuture<>();
        jobs.put(jobId, new PendingJob(payload, future, System.currentTimeMillis()));

        JsonObject player = new JsonObject();
        player.addProperty("name", payload.player());
        player.addProperty("uuid", payload.uuid());
        player.addProperty("world", payload.world());
        player.addProperty("x", payload.x());
        player.addProperty("y", payload.y());
        player.addProperty("z", payload.z());
        player.addProperty("yaw", payload.yaw());
        player.addProperty("pitch", payload.pitch());
        player.addProperty("gamemode", payload.gamemode());

        JsonObject body = new JsonObject();
        body.addProperty("prompt", payload.prompt());
        body.add("player", player);
        if (payload.observation() != null) {
            body.add("observation", payload.observation());
        }
        send(envelope(
                "job.submit",
                traceId,
                jobId,
                System.currentTimeMillis() + 10_000L,
                body
        )).exceptionally(error -> {
            PendingJob removed = jobs.remove(jobId);
            if (removed != null) {
                removed.future().complete(JobResult.fail("I couldn't send that request. Try again."));
            }
            return null;
        });
        return future.orTimeout(12, java.util.concurrent.TimeUnit.SECONDS)
                .exceptionally(error -> {
                    jobs.remove(jobId);
                    return JobResult.fail("That took too long, so I stopped safely.");
                });
    }

    @Override
    public void onOpen(WebSocket webSocket) {
        socket = webSocket;
        ready = false;
        sequence.set(0);
        WebSocket.Listener.super.onOpen(webSocket);
        JsonObject hello = new JsonObject();
        hello.addProperty("server_id", plugin.getConfig().getString("server-id", "neighborhood"));
        hello.addProperty("plugin_version", plugin.getPluginMeta().getVersion());
        hello.addProperty("minecraft_version", Bukkit.getMinecraftVersion());
        JsonArray capabilities = new JsonArray();
        tools.capabilities().forEach(capabilities::add);
        hello.add("capabilities", capabilities);
        send(envelope("hello", UUID.randomUUID().toString(), null, null, hello));
        plugin.getLogger().info("Connected companion gateway; waiting for handshake");
    }

    @Override
    public CompletionStage<?> onText(WebSocket webSocket, CharSequence data, boolean last) {
        synchronized (incoming) {
            incoming.append(data);
            if (last) {
                String message = incoming.toString();
                incoming.setLength(0);
                handleMessage(message);
            }
        }
        webSocket.request(1);
        return null;
    }

    @Override
    public CompletionStage<?> onClose(WebSocket webSocket, int statusCode, String reason) {
        socket = null;
        ready = false;
        failPending("Your sidekick disconnected. Please try again.");
        if (!closing.get()) {
            plugin.getLogger().warning("Companion disconnected (" + statusCode + "): " + reason);
            scheduleReconnect();
        }
        return WebSocket.Listener.super.onClose(webSocket, statusCode, reason);
    }

    @Override
    public void onError(WebSocket webSocket, Throwable error) {
        socket = null;
        ready = false;
        failPending("Your sidekick disconnected. Please try again.");
        if (!closing.get()) {
            plugin.getLogger().warning("Companion gateway error: " + rootMessage(error));
            scheduleReconnect();
        }
    }

    private void handleMessage(String raw) {
        try {
            JsonObject message = JsonParser.parseString(raw).getAsJsonObject();
            String type = message.get("type").getAsString();
            switch (type) {
                case "hello.ack" -> {
                    ready = true;
                    plugin.getLogger().info("Companion gateway ready");
                }
                case "heartbeat" -> {
                    // Acknowledged by receipt.
                }
                case "action.execute" -> handleAction(message);
                case "observation.request" -> handleObservationRequest(message);
                case "job.complete" -> handleComplete(message);
                default -> plugin.getLogger().fine("Ignoring companion message: " + type);
            }
        } catch (RuntimeException error) {
            plugin.getLogger().warning("Invalid companion message: " + error.getMessage());
        }
    }

    private void handleObservationRequest(JsonObject message) {
        String jobId = optionalString(message, "job_id");
        JsonObject payload = message.getAsJsonObject("payload");
        String purpose = payload.has("purpose") ? payload.get("purpose").getAsString() : "model_context";
        String parentId = payload.has("parent_observation_id")
                ? payload.get("parent_observation_id").getAsString()
                : null;
        PendingJob job = jobId == null ? null : jobs.get(jobId);
        if (job == null) {
            JsonObject failed = new JsonObject();
            failed.addProperty("ok", false);
            failed.addProperty("message", "That request is no longer active.");
            send(envelope(
                    "observation.result",
                    message.get("trace_id").getAsString(),
                    jobId,
                    optionalLong(message, "deadline_ms"),
                    failed
            ));
            return;
        }
        plugin.getServer().getScheduler().runTask(plugin, () -> {
            Player player = Bukkit.getPlayer(UUID.fromString(job.payload().uuid()));
            if (player == null || !player.isOnline()) {
                JsonObject failed = new JsonObject();
                failed.addProperty("ok", false);
                failed.addProperty("message", "You left before I could look around.");
                send(envelope(
                        "observation.result",
                        message.get("trace_id").getAsString(),
                        jobId,
                        optionalLong(message, "deadline_ms"),
                        failed
                ));
                return;
            }
            if (job.payload().observation() != null
                    && perception.isPoseStale(player, job.payload().observation())) {
                JsonObject failed = new JsonObject();
                failed.addProperty("ok", false);
                failed.addProperty("stale", true);
                failed.addProperty(
                        "message",
                        "Things moved while I was looking. Try: look at the corner and ask again."
                );
                send(envelope(
                        "observation.result",
                        message.get("trace_id").getAsString(),
                        jobId,
                        optionalLong(message, "deadline_ms"),
                        failed
                ));
                return;
            }
            String parent = parentId != null
                    ? parentId
                    : (job.payload().observation() != null
                            && job.payload().observation().has("observation_id")
                            ? job.payload().observation().get("observation_id").getAsString()
                            : UUID.randomUUID().toString());
            perception.inspectAsync(player, purpose, parent).whenComplete((scene, error) -> {
                JsonObject result = new JsonObject();
                if (error != null || scene == null) {
                    result.addProperty("ok", false);
                    result.addProperty("message", "I couldn't look around safely. Try again.");
                } else {
                    result.addProperty("ok", true);
                    result.add("scene", scene);
                    result.addProperty("queue_depth", perception.queueDepth());
                    result.addProperty("active", perception.activeCount());
                }
                send(envelope(
                        "observation.result",
                        message.get("trace_id").getAsString(),
                        jobId,
                        optionalLong(message, "deadline_ms"),
                        result
                ));
            });
        });
    }

    private void handleAction(JsonObject message) {
        String jobId = optionalString(message, "job_id");
        JsonObject payload = message.getAsJsonObject("payload");
        String actionId = payload.get("action_id").getAsString();
        String idempotencyKey = payload.get("idempotency_key").getAsString();
        JsonObject prior = journal.get(idempotencyKey);
        if (prior != null) {
            sendActionResult(message, prior);
            return;
        }
        PendingJob job = jobs.get(jobId);
        if (job == null) {
            sendActionResult(message, resultPayload(
                    actionId,
                    NativeToolRegistry.ToolResult.fail("That request is no longer active.", 0)
            ));
            return;
        }
        Long deadline = optionalLong(message, "deadline_ms");
        if (deadline != null && System.currentTimeMillis() > deadline) {
            sendActionResult(message, resultPayload(
                    actionId,
                    NativeToolRegistry.ToolResult.fail("That request expired before changing the world.", 0)
            ));
            return;
        }
        plugin.getServer().getScheduler().runTask(plugin, () -> {
            Player player = Bukkit.getPlayer(UUID.fromString(job.payload().uuid()));
            if (player == null || !player.isOnline()) {
                JsonObject resultJson = resultPayload(
                        actionId,
                        NativeToolRegistry.ToolResult.fail("You left before I could finish.", 0)
                );
                journal.put(idempotencyKey, resultJson);
                sendActionResult(message, resultJson);
                return;
            }
            tools.executeAsync(
                    player,
                    payload.get("tool").getAsString(),
                    payload.getAsJsonObject("arguments")
            ).whenComplete((result, error) -> {
                NativeToolRegistry.ToolResult completed = error == null
                        ? result
                        : NativeToolRegistry.ToolResult.fail("I couldn't finish that safely.", 0);
                JsonObject resultJson = resultPayload(actionId, completed);
                journal.put(idempotencyKey, resultJson);
                sendActionResult(message, resultJson);
            });
        });
    }

    private void sendActionResult(JsonObject request, JsonObject result) {
        send(envelope(
                "action.result",
                request.get("trace_id").getAsString(),
                optionalString(request, "job_id"),
                optionalLong(request, "deadline_ms"),
                result
        ));
    }

    private void handleComplete(JsonObject message) {
        String jobId = optionalString(message, "job_id");
        PendingJob job = jobs.remove(jobId);
        if (job == null) {
            return;
        }
        JsonObject payload = message.getAsJsonObject("payload");
        boolean ok = payload.has("ok") && payload.get("ok").getAsBoolean();
        String text = payload.has("message") ? payload.get("message").getAsString() : "Done.";
        boolean verified = payload.has("verified") && payload.get("verified").getAsBoolean();
        int totalMs = payload.has("total_ms") ? payload.get("total_ms").getAsInt() : 0;
        job.future().complete(new JobResult(ok, text, verified, totalMs));
    }

    private void sendHeartbeat() {
        if (!isReady()) {
            return;
        }
        send(envelope(
                "heartbeat",
                UUID.randomUUID().toString(),
                null,
                null,
                new JsonObject()
        ));
    }

    private CompletableFuture<WebSocket> send(JsonObject message) {
        WebSocket current = socket;
        if (current == null) {
            return CompletableFuture.failedFuture(new IllegalStateException("gateway offline"));
        }
        return current.sendText(GSON.toJson(message), true);
    }

    private JsonObject envelope(
            String type,
            String traceId,
            String jobId,
            Long deadlineMs,
            JsonObject payload
    ) {
        JsonObject message = new JsonObject();
        message.addProperty("protocol", PROTOCOL);
        message.addProperty("type", type);
        message.addProperty("trace_id", traceId);
        if (jobId == null) {
            message.add("job_id", null);
        } else {
            message.addProperty("job_id", jobId);
        }
        message.addProperty("sequence", sequence.incrementAndGet());
        message.addProperty("sent_at_ms", System.currentTimeMillis());
        if (deadlineMs == null) {
            message.add("deadline_ms", null);
        } else {
            message.addProperty("deadline_ms", deadlineMs);
        }
        message.add("payload", payload);
        return message;
    }

    private static JsonObject resultPayload(
            String actionId,
            NativeToolRegistry.ToolResult result
    ) {
        JsonObject payload = new JsonObject();
        payload.addProperty("action_id", actionId);
        payload.addProperty("ok", result.ok());
        payload.addProperty("executed", result.executed());
        payload.addProperty("verified", result.verified());
        payload.addProperty("message", result.message());
        payload.addProperty("execution_ms", result.executionMs());
        payload.add("data", new JsonObject());
        return payload;
    }

    private void failPending(String message) {
        jobs.forEach((ignored, job) -> job.future().complete(JobResult.fail(message)));
        jobs.clear();
    }

    private static String optionalString(JsonObject object, String key) {
        return object.has(key) && !object.get(key).isJsonNull()
                ? object.get(key).getAsString()
                : null;
    }

    private static Long optionalLong(JsonObject object, String key) {
        return object.has(key) && !object.get(key).isJsonNull()
                ? object.get(key).getAsLong()
                : null;
    }

    private static String rootMessage(Throwable error) {
        Throwable current = error;
        while (current.getCause() != null) {
            current = current.getCause();
        }
        return current.getMessage() == null ? current.getClass().getSimpleName() : current.getMessage();
    }

    @Override
    public void close() {
        closing.set(true);
        ready = false;
        failPending("Your sidekick is restarting.");
        WebSocket current = socket;
        socket = null;
        if (current != null) {
            current.sendClose(WebSocket.NORMAL_CLOSURE, "plugin disabled");
        }
    }

    public record JobPayload(
            String player,
            String uuid,
            String world,
            double x,
            double y,
            double z,
            float yaw,
            float pitch,
            String gamemode,
            String prompt,
            JsonObject observation
    ) {
        static JobPayload from(Player player, String prompt, PerceptionEngine perception) {
            var location = player.getLocation();
            GameMode mode = player.getGameMode();
            JsonObject observation = perception.captureFast(player);
            return new JobPayload(
                    player.getName(),
                    player.getUniqueId().toString(),
                    player.getWorld().getKey().toString(),
                    location.getX(),
                    location.getY(),
                    location.getZ(),
                    location.getYaw(),
                    location.getPitch(),
                    mode.name().toLowerCase(),
                    prompt,
                    observation
            );
        }
    }

    public record JobResult(boolean ok, String message, boolean verified, int totalMs) {
        static JobResult fail(String message) {
            return new JobResult(false, message, false, 0);
        }
    }

    private record PendingJob(
            JobPayload payload,
            CompletableFuture<JobResult> future,
            long submittedAtMs
    ) {
    }
}
