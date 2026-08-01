package com.neighborhood.agent;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.logging.Logger;

/**
 * Loads curated template titles + follow_up steps from catalog.json so chat
 * never exposes snake_case ids and animal pens can spawn their critters.
 */
final class TemplateCatalog {
    record FollowUpSummon(String entity, int count, int offsetY) {
    }

    record Entry(String id, String title, List<FollowUpSummon> followUps) {
    }

    private final Map<String, Entry> byId;

    private TemplateCatalog(Map<String, Entry> byId) {
        this.byId = byId;
    }

    static TemplateCatalog load(Path path, Logger logger) {
        if (path == null || !Files.isRegularFile(path)) {
            logger.warning("Template catalog missing at " + path + "; using id fallbacks");
            return new TemplateCatalog(Map.of());
        }
        try {
            String raw = Files.readString(path, StandardCharsets.UTF_8);
            JsonObject root = JsonParser.parseString(raw).getAsJsonObject();
            JsonArray templates = root.has("templates") ? root.getAsJsonArray("templates") : new JsonArray();
            Map<String, Entry> map = new HashMap<>();
            for (JsonElement element : templates) {
                if (!element.isJsonObject()) {
                    continue;
                }
                JsonObject item = element.getAsJsonObject();
                if (!item.has("id")) {
                    continue;
                }
                String id = item.get("id").getAsString();
                String title = item.has("title") ? item.get("title").getAsString() : id.replace('_', ' ');
                List<FollowUpSummon> followUps = parseFollowUps(item);
                map.put(id, new Entry(id, title, followUps));
            }
            logger.info("Loaded " + map.size() + " template catalog entries");
            return new TemplateCatalog(Collections.unmodifiableMap(map));
        } catch (IOException | RuntimeException error) {
            logger.warning("Failed to load template catalog: " + error.getMessage());
            return new TemplateCatalog(Map.of());
        }
    }

    private static List<FollowUpSummon> parseFollowUps(JsonObject item) {
        if (!item.has("follow_up") || !item.get("follow_up").isJsonArray()) {
            return List.of();
        }
        List<FollowUpSummon> out = new ArrayList<>();
        for (JsonElement element : item.getAsJsonArray("follow_up")) {
            if (!element.isJsonObject()) {
                continue;
            }
            JsonObject step = element.getAsJsonObject();
            String tool = step.has("tool") ? step.get("tool").getAsString() : "";
            if (!"summon_entity".equals(tool)) {
                continue;
            }
            String entity = step.has("entity") ? step.get("entity").getAsString() : "";
            int count = step.has("count") ? step.get("count").getAsInt() : 1;
            int offsetY = step.has("offset_y") ? step.get("offset_y").getAsInt() : 1;
            if (entity.isBlank() || count < 1) {
                continue;
            }
            out.add(new FollowUpSummon(entity.toLowerCase(Locale.ROOT), Math.min(count, 20), offsetY));
        }
        return List.copyOf(out);
    }

    String titleFor(String templateId) {
        Entry entry = byId.get(templateId);
        if (entry != null && entry.title() != null && !entry.title().isBlank()) {
            return entry.title();
        }
        return templateId.replace('_', ' ');
    }

    List<FollowUpSummon> followUpsFor(String templateId) {
        Entry entry = byId.get(templateId);
        return entry == null ? List.of() : entry.followUps();
    }

    static String withArticle(String title) {
        String trimmed = title == null ? "" : title.trim();
        if (trimmed.isEmpty()) {
            return "a build";
        }
        String readable = Character.toLowerCase(trimmed.charAt(0)) + trimmed.substring(1);
        char first = Character.toLowerCase(readable.charAt(0));
        String article = "aeiou".indexOf(first) >= 0 ? "an" : "a";
        return article + " " + readable;
    }
}
