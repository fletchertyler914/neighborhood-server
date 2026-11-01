package com.neighborhood.agent;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.logging.Logger;

/**
 * Append-only demotion log under the plugin data folder. Survives restarts.
 * Folded state: template ids currently demoted (last action wins).
 */
final class QaDemotionStore {
    private final Path path;
    private final Logger logger;
    private final Set<String> demoted = new LinkedHashSet<>();

    QaDemotionStore(Path path, Logger logger) {
        this.path = path;
        this.logger = logger;
        reload();
    }

    synchronized void reload() {
        demoted.clear();
        if (!Files.isRegularFile(path)) {
            return;
        }
        try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty()) {
                    continue;
                }
                try {
                    JsonObject row = JsonParser.parseString(line).getAsJsonObject();
                    String id = row.has("template_id") ? row.get("template_id").getAsString() : "";
                    String action = row.has("action") ? row.get("action").getAsString() : "demote";
                    if (id.isBlank()) {
                        continue;
                    }
                    if ("promote".equalsIgnoreCase(action)) {
                        demoted.remove(id);
                    } else {
                        demoted.add(id);
                    }
                } catch (RuntimeException ignored) {
                    // skip corrupt lines
                }
            }
        } catch (IOException error) {
            logger.warning("Could not read qa-demotions.jsonl: " + error.getMessage());
        }
    }

    synchronized boolean isDemoted(String templateId) {
        return demoted.contains(templateId);
    }

    /**
     * @return true if state changed (newly demoted), false if already demoted
     */
    synchronized boolean demote(String templateId, String player, boolean wasGold) {
        boolean already = demoted.contains(templateId);
        if (already) {
            return false;
        }
        append("demote", templateId, player, wasGold);
        demoted.add(templateId);
        return true;
    }

    /**
     * @return true if state changed (was demoted), false if not demoted
     */
    synchronized boolean promote(String templateId, String player, boolean wasGold) {
        boolean was = demoted.contains(templateId);
        if (!was) {
            return false;
        }
        append("promote", templateId, player, wasGold);
        demoted.remove(templateId);
        return true;
    }

    private void append(String action, String templateId, String player, boolean wasGold) {
        try {
            Files.createDirectories(path.getParent());
            JsonObject row = new JsonObject();
            row.addProperty("ts_ms", System.currentTimeMillis());
            row.addProperty("action", action);
            row.addProperty("template_id", templateId);
            row.addProperty("player", player == null ? "" : player);
            row.addProperty("was_gold", wasGold);
            try (BufferedWriter writer = Files.newBufferedWriter(
                    path,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND
            )) {
                writer.write(row.toString());
                writer.newLine();
            }
        } catch (IOException error) {
            logger.warning("Could not append qa-demotions.jsonl: " + error.getMessage());
        }
    }

    static String displayWasGold(boolean wasGold) {
        return wasGold ? "gold" : "not gold";
    }
}
