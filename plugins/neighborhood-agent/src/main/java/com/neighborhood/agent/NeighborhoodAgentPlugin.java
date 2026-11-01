package com.neighborhood.agent;

import org.bukkit.Material;
import org.bukkit.plugin.java.JavaPlugin;

import java.nio.file.Path;

public final class NeighborhoodAgentPlugin extends JavaPlugin {

    private static final String DEFAULT_DISPLAY_NAME = "Crafter";

    private CompanionGateway gateway;
    private BuildBrowser buildBrowser;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        gateway = new CompanionGateway(this);
        BuildBookItem bookItem = new BuildBookItem(this, getDisplayName());
        BuildBrowserSessions browserSessions = new BuildBrowserSessions();
        buildBrowser = new BuildBrowser(this, gateway, bookItem, browserSessions);
        getServer().getPluginManager().registerEvents(
                new BuildBrowserListener(this, buildBrowser, getDisplayName()),
                this
        );
        BuildsCommand buildsCommand = new BuildsCommand(buildBrowser, getDisplayName());
        var builds = getCommand("builds");
        if (builds != null) {
            builds.setExecutor(buildsCommand);
            builds.setTabCompleter(buildsCommand);
        } else {
            getLogger().severe("Command 'builds' missing from plugin.yml");
        }

        AgentCommand agentCommand = new AgentCommand(this, gateway, buildBrowser);
        var cmd = getCommand("agent");
        if (cmd != null) {
            cmd.setExecutor(agentCommand);
            cmd.setTabCompleter(agentCommand);
        } else {
            getLogger().severe("Command 'agent' missing from plugin.yml");
        }

        AgentAsCommand agentAsCommand = new AgentAsCommand(this, gateway);
        var agentAs = getCommand("agent-as");
        if (agentAs != null) {
            agentAs.setExecutor(agentAsCommand);
        } else {
            getLogger().severe("Command 'agent-as' missing from plugin.yml");
        }

        AgentPasteCommand agentPasteCommand = new AgentPasteCommand(this, gateway);
        var agentPaste = getCommand("agent-paste");
        if (agentPaste != null) {
            agentPaste.setExecutor(agentPasteCommand);
        } else {
            getLogger().severe("Command 'agent-paste' missing from plugin.yml");
        }
        var agentPasteAt = getCommand("agent-paste-at");
        if (agentPasteAt != null) {
            agentPasteAt.setExecutor(agentPasteCommand);
        } else {
            getLogger().severe("Command 'agent-paste-at' missing from plugin.yml");
        }

        AgentClearCommand agentClearCommand = new AgentClearCommand(this);
        var agentClear = getCommand("agent-clear-box");
        if (agentClear != null) {
            agentClear.setExecutor(agentClearCommand);
        } else {
            getLogger().severe("Command 'agent-clear-box' missing from plugin.yml");
        }

        getServer().getPluginManager().registerEvents(new LavaGuardListener(), this);
        getServer().getPluginManager().registerEvents(
                new PathMarkerListener(gateway.pathMarkerSessions(), getDisplayName()),
                this
        );
        registerQaDemote();

        QaHoeCommand qaHoeCommand = new QaHoeCommand(this);
        var qaHoe = getCommand("qa-hoe");
        if (qaHoe != null) {
            qaHoe.setExecutor(qaHoeCommand);
        } else {
            getLogger().severe("Command 'qa-hoe' missing from plugin.yml");
        }

        gateway.start();
        getLogger().info(
                "Neighborhood " + getDisplayName() + " enabled -> " + gateway.getGatewayUrl()
        );
    }

    private void registerQaDemote() {
        Path gridPath = getDataFolder().toPath().resolve(
                getConfig().getString("qa-grid-file", "qa-grid.json")
        );
        QaGridIndex grid = QaGridIndex.load(gridPath, getLogger());
        QaDemotionStore store = new QaDemotionStore(
                getDataFolder().toPath().resolve("qa-demotions.jsonl"),
                getLogger()
        );
        Material demoteItem = QaDemoteListener.materialOr(
                getConfig().getString("qa-demote-item", "WOODEN_HOE"),
                Material.WOODEN_HOE
        );
        Material promoteItem = QaDemoteListener.materialOr(
                getConfig().getString("qa-promote-item", "WOODEN_HOE"),
                demoteItem
        );
        getServer().getPluginManager().registerEvents(
                new QaDemoteListener(this, grid, store, demoteItem, promoteItem),
                this
        );
        getLogger().info(
                "QA demote: item=" + demoteItem + " promote=" + promoteItem
                        + " gridReady=" + grid.ready()
        );
    }

    @Override
    public void onDisable() {
        if (gateway != null) {
            gateway.close();
        }
    }

    /** Kid-facing chat/boss-bar name from config.yml (`display-name`). */
    public String getDisplayName() {
        String configured = getConfig().getString("display-name", DEFAULT_DISPLAY_NAME);
        if (configured == null || configured.isBlank()) {
            return DEFAULT_DISPLAY_NAME;
        }
        return configured.trim();
    }

    public CompanionGateway getGateway() {
        return gateway;
    }

    public BuildBrowser getBuildBrowser() {
        return buildBrowser;
    }
}
