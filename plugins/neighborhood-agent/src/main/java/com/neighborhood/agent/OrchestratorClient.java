package com.neighborhood.agent;

import org.bukkit.plugin.java.JavaPlugin;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

public final class OrchestratorClient implements AutoCloseable {

    private final JavaPlugin plugin;
    private final HttpClient http;

    public OrchestratorClient(JavaPlugin plugin) {
        this.plugin = plugin;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
    }

    public String getBaseUrl() {
        return plugin.getConfig().getString("orchestrator-url", "http://mc-agent:8787");
    }

    private String getApiToken() {
        String configured = plugin.getConfig().getString("api-token", "env:AGENT_API_TOKEN");
        if (configured != null && configured.startsWith("env:")) {
            String envName = configured.substring("env:".length());
            String envValue = System.getenv(envName);
            if (envValue != null && !envValue.isBlank()) {
                return envValue;
            }
            plugin.getLogger().severe(
                    "Environment variable " + envName + " is not set; /agent is disabled until AGENT_API_TOKEN is configured");
            return "";
        }
        if (configured == null || configured.isBlank()) {
            plugin.getLogger().severe("api-token is not set in plugin config; /agent is disabled");
            return "";
        }
        return configured;
    }

    private int getTimeoutSec() {
        return plugin.getConfig().getInt("job-timeout-seconds", 180);
    }

    public CompletableFuture<JobResult> submitJob(JobPayload payload) {
        String token = getApiToken();
        if (token.isBlank()) {
            return CompletableFuture.completedFuture(
                    JobResult.fail("Agent misconfigured: set AGENT_API_TOKEN in .env and restart the stack"));
        }
        String url = getBaseUrl().replaceAll("/$", "") + "/v1/jobs";
        String body = payload.toJson();
        int timeout = getTimeoutSec();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(timeout))
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + token)
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        return http.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenApply(resp -> {
                    if (resp.statusCode() == 429) {
                        return JobResult.fail("Rate limited. Wait a few seconds and try again.");
                    }
                    if (resp.statusCode() >= 400) {
                        return JobResult.fail("Orchestrator error HTTP " + resp.statusCode() + ": " + resp.body());
                    }
                    return JobResult.parse(resp.body());
                })
                .exceptionally(ex -> {
                    String msg = ex.getMessage() != null ? ex.getMessage() : ex.getClass().getSimpleName();
                    if (msg.contains("Connection refused") || msg.contains("connect")) {
                        return JobResult.fail(
                                "Agent offline. Check: docker compose ps mc-agent && docker compose logs mc-agent");
                    }
                    return JobResult.fail("Agent request failed: " + msg);
                });
    }

    @Override
    public void close() {
        // HttpClient has no close in Java 11+ for default impl
    }

    public record JobPayload(
            String player,
            String uuid,
            String world,
            double x,
            double y,
            double z,
            String gamemode,
            String prompt
    ) {
        String toJson() {
            return "{"
                    + "\"player\":\"" + escape(player) + "\","
                    + "\"uuid\":\"" + escape(uuid) + "\","
                    + "\"world\":\"" + escape(world) + "\","
                    + "\"x\":" + x + ","
                    + "\"y\":" + y + ","
                    + "\"z\":" + z + ","
                    + "\"gamemode\":\"" + escape(gamemode) + "\","
                    + "\"prompt\":\"" + escape(prompt) + "\""
                    + "}";
        }

        private static String escape(String s) {
            return s.replace("\\", "\\\\").replace("\"", "\\\"");
        }
    }

    public static final class JobResult {
        public final boolean ok;
        public final String message;
        public final String model;
        public final int steps;

        private JobResult(boolean ok, String message, String model, int steps) {
            this.ok = ok;
            this.message = message;
            this.model = model;
            this.steps = steps;
        }

        static JobResult fail(String message) {
            return new JobResult(false, message, "", 0);
        }

        static JobResult parse(String json) {
            // Minimal JSON parse without extra dependencies
            String message = extract(json, "message");
            String model = extract(json, "model");
            int steps = 0;
            try {
                String stepsStr = extract(json, "steps");
                if (!stepsStr.isEmpty()) {
                    steps = Integer.parseInt(stepsStr);
                }
            } catch (NumberFormatException ignored) {
            }
            String status = extract(json, "status");
            boolean ok = !"failed".equals(status);
            if (message.isEmpty()) {
                message = ok ? "Done." : "Job failed.";
            }
            return new JobResult(ok, message, model, steps);
        }

        private static String extract(String json, String key) {
            String needle = "\"" + key + "\":";
            int i = json.indexOf(needle);
            if (i < 0) {
                return "";
            }
            i += needle.length();
            while (i < json.length() && Character.isWhitespace(json.charAt(i))) {
                i++;
            }
            if (i >= json.length()) {
                return "";
            }
            if (json.charAt(i) == '"') {
                i++;
                StringBuilder sb = new StringBuilder();
                while (i < json.length()) {
                    char c = json.charAt(i);
                    if (c == '\\' && i + 1 < json.length()) {
                        sb.append(json.charAt(i + 1));
                        i += 2;
                        continue;
                    }
                    if (c == '"') {
                        break;
                    }
                    sb.append(c);
                    i++;
                }
                return sb.toString();
            }
            int end = i;
            while (end < json.length() && json.charAt(end) != ',' && json.charAt(end) != '}') {
                end++;
            }
            return json.substring(i, end).trim();
        }
    }
}
