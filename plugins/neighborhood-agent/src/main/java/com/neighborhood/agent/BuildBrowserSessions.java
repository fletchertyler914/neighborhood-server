package com.neighborhood.agent;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Per-player Build Book UI / search / clear-confirm state.
 */
final class BuildBrowserSessions {

    enum Mode {
        /** Waiting for a chat filter line after clicking Search. */
        SEARCH_CHAT,
        /** Waiting for yes/cancel after paste needs site clear. */
        CLEAR_CONFIRM
    }

    record Session(
            Mode mode,
            TemplateCatalog.Bucket bucket,
            String filter,
            int page,
            String pendingTemplateId,
            long startedMs
    ) {
        static Session search(TemplateCatalog.Bucket bucket, String filter, int page) {
            return new Session(Mode.SEARCH_CHAT, bucket, filter == null ? "" : filter, page, null, System.currentTimeMillis());
        }

        static Session clearConfirm(String templateId) {
            return new Session(Mode.CLEAR_CONFIRM, null, "", 1, templateId, System.currentTimeMillis());
        }
    }

    private static final long TTL_MS = 120_000L;

    private final Map<UUID, Session> sessions = new ConcurrentHashMap<>();

    void put(UUID playerId, Session session) {
        sessions.put(playerId, session);
    }

    Session get(UUID playerId) {
        Session session = sessions.get(playerId);
        if (session == null) {
            return null;
        }
        if (System.currentTimeMillis() - session.startedMs() > TTL_MS) {
            sessions.remove(playerId, session);
            return null;
        }
        return session;
    }

    Session take(UUID playerId) {
        Session session = get(playerId);
        if (session != null) {
            sessions.remove(playerId);
        }
        return session;
    }

    void clear(UUID playerId) {
        sessions.remove(playerId);
    }

    boolean isSearching(UUID playerId) {
        Session session = get(playerId);
        return session != null && session.mode() == Mode.SEARCH_CHAT;
    }
}
