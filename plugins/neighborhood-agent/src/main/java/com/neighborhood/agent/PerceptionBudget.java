package com.neighborhood.agent;

final class PerceptionBudget {
    static final int GAZE_RAY_BLOCKS = 48;
    /** Max horizontal scan while hunting for a far post/edge. */
    static final int SCAN_HORIZONTAL = 48;
    /** Reject openings longer than this (inclusive of both posts). */
    static final int MAX_OPENING_LENGTH = 48;
    static final int SCAN_VERTICAL = 128;
    static final int PALETTE_RADIUS = 16;
    static final int MAX_CELLS = 20_000;
    static final int MAX_BYTES = 8 * 1024;
    static final int MAIN_THREAD_SLICE_MS = 10;
    static final int FAST_HARD_MAX_MS = 10;
    /** Soft cap for deep scans; opening detection may continue briefly past this. */
    static final int DEEP_HARD_MAX_MS = 80;
    static final int MAX_ACTIVE_PER_PLAYER = 1;
    static final int MAX_ACTIVE_SERVER = 2;
    static final int MAX_QUEUE = 8;
    static final double STALE_MOVE_BLOCKS = 2.0;
    static final float STALE_YAW_DEGREES = 30.0f;
    static final long OBSERVATION_TTL_MS = 10_000L;

    private int cellsSampled;
    private long startedNanos;
    private boolean truncated;

    PerceptionBudget() {
        reset();
    }

    void reset() {
        cellsSampled = 0;
        startedNanos = System.nanoTime();
        truncated = false;
    }

    boolean sampleCell() {
        cellsSampled++;
        if (cellsSampled > MAX_CELLS || elapsedMs() >= DEEP_HARD_MAX_MS) {
            truncated = true;
            // Still allow a short overrun so an in-progress opening can finish.
            return cellsSampled <= MAX_CELLS && elapsedMs() < DEEP_HARD_MAX_MS + 40;
        }
        return true;
    }

    int cellsSampled() {
        return cellsSampled;
    }

    boolean truncated() {
        return truncated;
    }

    int elapsedMs() {
        return (int) ((System.nanoTime() - startedNanos) / 1_000_000L);
    }

    void markTruncated() {
        truncated = true;
    }
}
