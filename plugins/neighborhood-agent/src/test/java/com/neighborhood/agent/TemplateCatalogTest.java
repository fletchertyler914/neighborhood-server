package com.neighborhood.agent;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.logging.Logger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

final class TemplateCatalogTest {

    private static final String FIXTURE = """
            {
              "version": 1,
              "templates": [
                {
                  "id": "chicken_coop_small",
                  "title": "Chicken coop",
                  "category": "farm",
                  "complexity": "basic",
                  "tags": ["animals", "coop"],
                  "aliases": ["chicken coop", "chiken coop"],
                  "footprint": [9, 6, 9],
                  "max_blocks": 120,
                  "gold": true,
                  "follow_up": []
                },
                {
                  "id": "cottage_medium",
                  "title": "Medium cottage",
                  "category": "house",
                  "complexity": "common",
                  "tags": ["home"],
                  "aliases": ["cottage"],
                  "footprint": [9, 7, 9],
                  "max_blocks": 200,
                  "gold": true,
                  "follow_up": []
                },
                {
                  "id": "apartment_block",
                  "title": "Apartment",
                  "category": "house",
                  "complexity": "complex",
                  "tags": [],
                  "aliases": [],
                  "footprint": [12, 20, 12],
                  "max_blocks": 900,
                  "follow_up": []
                }
              ]
            }
            """;

    @Test
    void loadsGoldOnlyForBrowse() {
        TemplateCatalog catalog = TemplateCatalog.parse(
                FIXTURE, 1L, null, Logger.getLogger("test")
        );
        assertEquals(2, catalog.allGold().size());
        assertEquals(1, catalog.byBucket(TemplateCatalog.Bucket.FARMS).size());
        assertEquals(1, catalog.byBucket(TemplateCatalog.Bucket.HOUSES).size());
        assertEquals("Chicken coop", catalog.titleFor("chicken_coop_small"));
        assertFalse(catalog.entry("apartment_block").gold());
    }

    @Test
    void searchMatchesTitleAliasAndTags() {
        TemplateCatalog catalog = TemplateCatalog.parse(
                FIXTURE, 1L, null, Logger.getLogger("test")
        );
        List<TemplateCatalog.Entry> byAlias = catalog.search("chiken");
        assertEquals(1, byAlias.size());
        assertEquals("chicken_coop_small", byAlias.get(0).id());

        List<TemplateCatalog.Entry> byTag = catalog.search("animals");
        assertEquals(1, byTag.size());

        List<TemplateCatalog.Entry> cottage = catalog.search("cottage", TemplateCatalog.Bucket.HOUSES);
        assertEquals(1, cottage.size());
        assertEquals("cottage_medium", cottage.get(0).id());

        assertTrue(catalog.search("castle").isEmpty());
        assertEquals(2, catalog.search("").size());
    }

    @Test
    void bucketMappingMatchesHelpBuckets() {
        assertEquals(
                TemplateCatalog.Bucket.BRIDGES,
                TemplateCatalog.Bucket.fromCatalogCategory("infrastructure")
        );
        assertEquals(
                TemplateCatalog.Bucket.PARKS,
                TemplateCatalog.Bucket.fromCatalogCategory("decoration")
        );
        assertEquals("farms", TemplateCatalog.Bucket.FARMS.id);
    }
}
