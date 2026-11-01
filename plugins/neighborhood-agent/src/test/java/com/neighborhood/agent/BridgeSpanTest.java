package com.neighborhood.agent;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

final class BridgeSpanTest {

    @Test
    void groundHugStaysOnGradeWhenThresholdOneBelow() {
        // Outdoor support often sits one above door.getY()-1 — must not trench.
        int startY = 65;
        int endY = 64;
        int len = 15;
        int[] terrain = flat(len, 65);
        int[] ys = BridgeSpan.stairProfileGroundHug(terrain, startY, endY);
        int rampStart = BridgeSpan.groundHugRampStart(terrain, startY, endY);
        assertEquals(endY, ys[ys.length - 1]);
        assertEquals(startY, ys[0]);
        for (int i = 0; i < rampStart; i++) {
            assertTrue(ys[i] >= terrain[i], "approach must not dig under grade at " + i);
            assertEquals(65, ys[i], "approach must stay on outdoor grade at index " + i);
        }
        for (int i = 0; i < ys.length - 1; i++) {
            assertTrue(Math.abs(ys[i + 1] - ys[i]) <= BridgeSpan.MAX_STEP);
        }
    }

    @Test
    void groundHugRisesLateToElevatedDoor() {
        int startY = 64;
        int endY = 70;
        int len = 20;
        int[] terrain = flat(len, 64);
        int[] ys = BridgeSpan.stairProfileGroundHug(terrain, startY, endY);
        assertEquals(startY, ys[0]);
        assertEquals(endY, ys[ys.length - 1]);
        int onGrade = 0;
        for (int y : ys) {
            if (y == 64) {
                onGrade++;
            }
            assertTrue(y >= 64, "must not dig below outdoor grade");
        }
        assertTrue(onGrade >= 12, "expected late rise, on-grade steps=" + onGrade);
        for (int i = 1; i < ys.length; i++) {
            assertTrue(Math.abs(ys[i] - ys[i - 1]) <= BridgeSpan.MAX_STEP);
        }
    }

    @Test
    void linearClampWouldTrenchButGroundHugDoesNot() {
        int startY = 70;
        int endY = 64;
        int len = 20;
        int[] terrain = flat(len, 70);
        int[] hugged = BridgeSpan.stairProfileGroundHug(terrain, startY, endY);
        int rampStart = BridgeSpan.groundHugRampStart(terrain, startY, endY);
        int[] linear = BridgeSpan.stairProfile(len, startY, endY);
        // Simulate the old buggy "hard clamp to endY".
        int[] clamped = new int[linear.length];
        for (int i = 0; i < linear.length; i++) {
            clamped[i] = Math.min(linear[i], endY);
        }
        int clampedBelow = 0;
        for (int y : clamped) {
            if (y < 70) {
                clampedBelow++;
            }
        }
        assertTrue(clampedBelow >= 15, "sanity: old clamp trenches most of the run");

        int approachBelow = 0;
        for (int i = 0; i < rampStart; i++) {
            if (hugged[i] < terrain[i]) {
                approachBelow++;
            }
        }
        assertEquals(0, approachBelow, "approach must never sit under grade");
        assertTrue(rampStart >= 14, "descent reserved for a short suffix, rampStart=" + rampStart);
        assertEquals(endY, hugged[hugged.length - 1]);
    }

    @Test
    void approachNeverUnderGradeWhenDoorBelow() {
        // Outdoor start above sill: approach stays on grade; only suffix may dip.
        int[][] cases = {
                {65, 64, 15},
                {70, 64, 20},
                {68, 64, 16},
        };
        for (int[] c : cases) {
            int startY = c[0];
            int endY = c[1];
            int len = c[2];
            int[] terrain = flat(len, startY);
            int[] hugged = BridgeSpan.stairProfileGroundHug(terrain, startY, endY);
            int rampStart = BridgeSpan.groundHugRampStart(terrain, startY, endY);
            assertTrue(rampStart >= len - Math.abs(endY - startY));
            for (int i = 0; i < rampStart; i++) {
                assertTrue(
                        hugged[i] >= terrain[i],
                        "under grade at " + i + " for start=" + startY
                );
            }
            assertEquals(endY, hugged[len - 1]);
            for (int i = 1; i < len; i++) {
                assertTrue(Math.abs(hugged[i] - hugged[i - 1]) <= BridgeSpan.MAX_STEP);
            }
        }
    }

    @Test
    void hardEndYClampStillTheOriginalTrench() {
        int len = 20;
        int startY = 70;
        int endY = 64;
        int[] linear = BridgeSpan.stairProfile(len, startY, endY);
        int clampedBelow = 0;
        for (int y : linear) {
            if (Math.min(y, endY) < startY) {
                clampedBelow++;
            }
        }
        assertTrue(clampedBelow >= 15, "sanity: hard endY clamp trenches");
        int[] terrain = flat(len, startY);
        int[] hugged = BridgeSpan.stairProfileGroundHug(terrain, startY, endY);
        int rampStart = BridgeSpan.groundHugRampStart(terrain, startY, endY);
        for (int i = 0; i < rampStart; i++) {
            assertTrue(hugged[i] >= startY);
        }
    }

    @Test
    void flatEqualThresholdNeverGoesUnderground() {
        int[] terrain = flat(12, 64);
        int[] ys = BridgeSpan.stairProfileGroundHug(terrain, 64, 64);
        for (int i = 0; i < ys.length; i++) {
            assertEquals(64, ys[i], "flat door must stay on grade at " + i);
        }
    }

    @Test
    void stairsUpNeverBelowTerrain() {
        int[] terrain = flat(20, 64);
        int[] ys = BridgeSpan.stairProfileGroundHug(terrain, 64, 70);
        for (int i = 0; i < ys.length; i++) {
            assertTrue(ys[i] >= terrain[i], "up-ramp under grade at " + i);
        }
        assertEquals(70, ys[ys.length - 1]);
    }

    @Test
    void preferWalkSurfaceRejectsLakebedUnderPier() {
        // Pier planks at 64, feet at 65, lakebed at 58, water top at 63.
        assertEquals(64, BridgeSpan.preferWalkSurface(65, 64, null, 4));
        assertEquals(64, BridgeSpan.preferWalkSurface(65, 58, 63, 4));
        // Lakebed under water → deck at max(waterTop, nearY-1).
        assertEquals(62, BridgeSpan.preferWalkSurface(63, 50, 62, 4));
        // Deep solid without water → stay at feet deck (nearY-1), not cave floor.
        assertEquals(64, BridgeSpan.preferWalkSurface(65, 40, null, 4));
    }

    @Test
    void trailFollowNeverUnderLandGrade() {
        assertEquals(70, BridgeSpan.trailFollowY(64, 70, false, 64));
        assertEquals(65, BridgeSpan.trailFollowY(65, 64, false, 64));
        // Water crossing keeps deck floor (pier height), not lakebed.
        assertEquals(65, BridgeSpan.trailFollowY(63, 62, true, 65));
    }

    @Test
    void pierStartStaysOnPlanksThroughWaterApproach() {
        // Simulated stairs-to-door from pier: start on planks, water columns,
        // then rising shore — approach must not sit on water/lakebed.
        int startY = 64;
        int endY = 70;
        int[] terrain = {
                64, 64, 64, 64, 64, 65, 66, 67, 68, 69, 70, 70
        };
        // Water stretch reported as water-top 63 must be lifted to startY by caller;
        // terrain here is already deck-corrected.
        int[] ys = BridgeSpan.stairProfileGroundHug(terrain, startY, endY);
        assertEquals(startY, ys[0]);
        int rampStart = BridgeSpan.groundHugRampStart(terrain, startY, endY);
        for (int i = 0; i < ys.length; i++) {
            assertTrue(ys[i] >= startY, "under pier deck at " + i);
        }
        for (int i = 0; i < rampStart; i++) {
            assertTrue(ys[i] >= terrain[i], "approach under grade at " + i);
        }
        assertEquals(endY, ys[ys.length - 1]);
    }

    @Test
    void ascendingHillProfileNeverExcavatesApproach() {
        int startY = 64;
        int endY = 72;
        // Steep face: terrain jumps faster than ±1 — profile climbs but must
        // not go under the start deck on the approach.
        int[] terrain = {64, 64, 68, 70, 72, 72, 72, 72, 72, 72};
        int[] ys = BridgeSpan.stairProfileGroundHug(terrain, startY, endY);
        assertEquals(startY, ys[0]);
        int rampStart = BridgeSpan.groundHugRampStart(terrain, startY, endY);
        for (int i = 0; i < rampStart; i++) {
            assertTrue(ys[i] >= startY, "approach under standing surface at " + i);
        }
        for (int i = 1; i < ys.length; i++) {
            assertTrue(Math.abs(ys[i] - ys[i - 1]) <= BridgeSpan.MAX_STEP);
        }
    }

    private static int[] flat(int len, int y) {
        int[] out = new int[len];
        java.util.Arrays.fill(out, y);
        return out;
    }
}
