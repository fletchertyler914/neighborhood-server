package com.neighborhood.agent;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.LinkedHashMap;
import java.util.Map;

final class IdempotencyJournal {
    private static final int MAX_ENTRIES = 1000;
    private static final Gson GSON = new Gson();

    private final NeighborhoodAgentPlugin plugin;
    private final LinkedHashMap<String, JsonObject> results = new LinkedHashMap<>();

    IdempotencyJournal(NeighborhoodAgentPlugin plugin) {
        this.plugin = plugin;
        load();
    }

    synchronized JsonObject get(String key) {
        JsonObject result = results.get(key);
        return result == null ? null : result.deepCopy();
    }

    synchronized void put(String key, JsonObject result) {
        results.put(key, result.deepCopy());
        while (results.size() > MAX_ENTRIES) {
            String oldest = results.keySet().iterator().next();
            results.remove(oldest);
        }
        plugin.getServer().getScheduler().runTaskAsynchronously(plugin, this::save);
    }

    private synchronized void load() {
        var path = plugin.getDataFolder().toPath().resolve("action-journal.json");
        if (!Files.exists(path)) {
            return;
        }
        try {
            JsonObject root = JsonParser.parseString(Files.readString(path)).getAsJsonObject();
            for (Map.Entry<String, com.google.gson.JsonElement> entry : root.entrySet()) {
                if (entry.getValue().isJsonObject()) {
                    results.put(entry.getKey(), entry.getValue().getAsJsonObject());
                }
            }
        } catch (Exception error) {
            plugin.getLogger().warning("Could not load action idempotency journal: " + error.getMessage());
        }
    }

    private synchronized void save() {
        try {
            Files.createDirectories(plugin.getDataFolder().toPath());
            var target = plugin.getDataFolder().toPath().resolve("action-journal.json");
            var temporary = plugin.getDataFolder().toPath().resolve("action-journal.json.tmp");
            JsonObject root = new JsonObject();
            results.forEach(root::add);
            Files.writeString(temporary, GSON.toJson(root));
            try {
                Files.move(
                        temporary,
                        target,
                        StandardCopyOption.REPLACE_EXISTING,
                        StandardCopyOption.ATOMIC_MOVE
                );
            } catch (IOException unsupportedAtomicMove) {
                Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException error) {
            plugin.getLogger().warning("Could not save action idempotency journal: " + error.getMessage());
        }
    }
}
