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
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.logging.Logger;

/**
 * Loads curated template metadata from catalog.json for chat titles,
 * follow-up summons, and the in-game Build Book browser (gold only).
 */
final class TemplateCatalog {
    record FollowUpSummon(String entity, int count, int offsetY) {
    }

    /** Kid-facing browse bucket (matches companion/help.py). */
    enum Bucket {
        HOUSES("houses", "Houses & shops", "house"),
        FARMS("farms", "Farms & animals", "farm"),
        FORTS("forts", "Forts & towers", "fortress"),
        BRIDGES("bridges", "Bridges & paths", "infrastructure"),
        PARKS("parks", "Parks & decor", "decoration"),
        NATURE("nature", "Nature", "nature_terrain"),
        UTILITY("utility", "Utility", "utility");

        final String id;
        final String label;
        final String catalogCategory;

        Bucket(String id, String label, String catalogCategory) {
            this.id = id;
            this.label = label;
            this.catalogCategory = catalogCategory;
        }

        static Bucket fromCatalogCategory(String category) {
            if (category == null || category.isBlank()) {
                return null;
            }
            String key = category.trim().toLowerCase(Locale.ROOT);
            for (Bucket bucket : values()) {
                if (bucket.catalogCategory.equals(key)) {
                    return bucket;
                }
            }
            return null;
        }

        static Bucket fromId(String id) {
            if (id == null || id.isBlank()) {
                return null;
            }
            String key = id.trim().toLowerCase(Locale.ROOT);
            for (Bucket bucket : values()) {
                if (bucket.id.equals(key)) {
                    return bucket;
                }
            }
            return null;
        }
    }

    record Entry(
            String id,
            String title,
            List<FollowUpSummon> followUps,
            boolean gold,
            String category,
            String complexity,
            List<String> tags,
            List<String> aliases,
            int[] footprint,
            int maxBlocks
    ) {
        Bucket bucket() {
            return Bucket.fromCatalogCategory(category);
        }
    }

    private final Map<String, Entry> byId;
    private final List<Entry> goldEntries;
    private final long loadedMtimeMs;
    private final Path sourcePath;
    private final Logger logger;

    private TemplateCatalog(
            Map<String, Entry> byId,
            List<Entry> goldEntries,
            long loadedMtimeMs,
            Path sourcePath,
            Logger logger
    ) {
        this.byId = byId;
        this.goldEntries = goldEntries;
        this.loadedMtimeMs = loadedMtimeMs;
        this.sourcePath = sourcePath;
        this.logger = logger;
    }

    static TemplateCatalog load(Path path, Logger logger) {
        if (path == null || !Files.isRegularFile(path)) {
            logger.warning("Template catalog missing at " + path + "; using id fallbacks");
            return new TemplateCatalog(Map.of(), List.of(), 0L, path, logger);
        }
        try {
            long mtime = Files.getLastModifiedTime(path).toMillis();
            String raw = Files.readString(path, StandardCharsets.UTF_8);
            return parse(raw, mtime, path, logger);
        } catch (IOException | RuntimeException error) {
            logger.warning("Failed to load template catalog: " + error.getMessage());
            return new TemplateCatalog(Map.of(), List.of(), 0L, path, logger);
        }
    }

    /** Parse catalog JSON (tests + load). */
    static TemplateCatalog parse(String raw, long mtimeMs, Path sourcePath, Logger logger) {
        JsonObject root = JsonParser.parseString(raw).getAsJsonObject();
        JsonArray templates = root.has("templates") ? root.getAsJsonArray("templates") : new JsonArray();
        Map<String, Entry> map = new HashMap<>();
        List<Entry> gold = new ArrayList<>();
        for (JsonElement element : templates) {
            if (!element.isJsonObject()) {
                continue;
            }
            JsonObject item = element.getAsJsonObject();
            if (!item.has("id")) {
                continue;
            }
            Entry entry = parseEntry(item);
            map.put(entry.id(), entry);
            if (entry.gold()) {
                gold.add(entry);
            }
        }
        gold.sort(Comparator.comparing(e -> e.title().toLowerCase(Locale.ROOT)));
        if (logger != null) {
            logger.info(
                    "Loaded " + map.size() + " template catalog entries ("
                            + gold.size() + " gold)"
            );
        }
        return new TemplateCatalog(
                Collections.unmodifiableMap(map),
                List.copyOf(gold),
                mtimeMs,
                sourcePath,
                logger
        );
    }

    private static Entry parseEntry(JsonObject item) {
        String id = item.get("id").getAsString();
        String title = item.has("title") ? item.get("title").getAsString() : id.replace('_', ' ');
        boolean gold = item.has("gold") && item.get("gold").getAsBoolean();
        String category = item.has("category") ? item.get("category").getAsString() : "";
        String complexity = item.has("complexity") ? item.get("complexity").getAsString() : "";
        List<String> tags = stringList(item, "tags");
        List<String> aliases = stringList(item, "aliases");
        int[] footprint = parseFootprint(item);
        int maxBlocks = item.has("max_blocks") && item.get("max_blocks").isJsonPrimitive()
                ? item.get("max_blocks").getAsInt()
                : 0;
        return new Entry(
                id,
                title,
                parseFollowUps(item),
                gold,
                category,
                complexity,
                tags,
                aliases,
                footprint,
                maxBlocks
        );
    }

    private static int[] parseFootprint(JsonObject item) {
        if (!item.has("footprint") || !item.get("footprint").isJsonArray()) {
            return new int[]{0, 0, 0};
        }
        JsonArray arr = item.getAsJsonArray("footprint");
        int w = arr.size() > 0 ? arr.get(0).getAsInt() : 0;
        int h = arr.size() > 1 ? arr.get(1).getAsInt() : 0;
        int d = arr.size() > 2 ? arr.get(2).getAsInt() : 0;
        return new int[]{w, h, d};
    }

    private static List<String> stringList(JsonObject item, String key) {
        if (!item.has(key) || !item.get(key).isJsonArray()) {
            return List.of();
        }
        List<String> out = new ArrayList<>();
        for (JsonElement element : item.getAsJsonArray(key)) {
            if (element.isJsonPrimitive()) {
                String value = element.getAsString().trim();
                if (!value.isEmpty()) {
                    out.add(value);
                }
            }
        }
        return List.copyOf(out);
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

    /**
     * Reload from disk when the catalog file mtime advanced (ops ingest).
     */
    TemplateCatalog refreshIfStale() {
        if (sourcePath == null || !Files.isRegularFile(sourcePath)) {
            return this;
        }
        try {
            long mtime = Files.getLastModifiedTime(sourcePath).toMillis();
            if (mtime <= loadedMtimeMs) {
                return this;
            }
            return load(sourcePath, logger != null ? logger : Logger.getLogger("TemplateCatalog"));
        } catch (IOException ignored) {
            return this;
        }
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

    Entry entry(String templateId) {
        return byId.get(templateId);
    }

    List<Entry> allGold() {
        return goldEntries;
    }

    List<Entry> byBucket(Bucket bucket) {
        if (bucket == null) {
            return allGold();
        }
        List<Entry> out = new ArrayList<>();
        for (Entry entry : goldEntries) {
            if (bucket.equals(entry.bucket())) {
                out.add(entry);
            }
        }
        return out;
    }

    /**
     * Case-insensitive token search over title, aliases, tags, and id.
     * Every whitespace-separated token must match somewhere.
     */
    List<Entry> search(String query) {
        return search(query, null);
    }

    List<Entry> search(String query, Bucket bucket) {
        String q = query == null ? "" : query.trim().toLowerCase(Locale.ROOT);
        List<Entry> base = byBucket(bucket);
        if (q.isEmpty()) {
            return base;
        }
        String[] tokens = q.split("\\s+");
        List<Entry> out = new ArrayList<>();
        for (Entry entry : base) {
            if (matchesAllTokens(entry, tokens)) {
                out.add(entry);
            }
        }
        return out;
    }

    private static boolean matchesAllTokens(Entry entry, String[] tokens) {
        String hay = haystack(entry);
        for (String token : tokens) {
            if (token.isEmpty()) {
                continue;
            }
            if (!hay.contains(token)) {
                return false;
            }
        }
        return true;
    }

    private static String haystack(Entry entry) {
        StringBuilder sb = new StringBuilder();
        sb.append(entry.id()).append(' ');
        sb.append(entry.title()).append(' ');
        sb.append(entry.category()).append(' ');
        sb.append(entry.complexity()).append(' ');
        for (String tag : entry.tags()) {
            sb.append(tag).append(' ');
        }
        for (String alias : entry.aliases()) {
            sb.append(alias).append(' ');
        }
        return sb.toString().toLowerCase(Locale.ROOT);
    }

    /** Stable category → entries map for browse home. */
    Map<Bucket, List<Entry>> goldByBucket() {
        Map<Bucket, List<Entry>> map = new LinkedHashMap<>();
        for (Bucket bucket : Bucket.values()) {
            map.put(bucket, byBucket(bucket));
        }
        return map;
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
