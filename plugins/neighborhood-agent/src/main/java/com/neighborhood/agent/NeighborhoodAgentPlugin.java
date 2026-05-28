package com.neighborhood.agent;

import org.bukkit.plugin.java.JavaPlugin;

public final class NeighborhoodAgentPlugin extends JavaPlugin {

    private OrchestratorClient orchestrator;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        orchestrator = new OrchestratorClient(this);
        AgentCommand agentCommand = new AgentCommand(this, orchestrator);
        var cmd = getCommand("agent");
        if (cmd != null) {
            cmd.setExecutor(agentCommand);
            cmd.setTabCompleter(agentCommand);
        } else {
            getLogger().severe("Command 'agent' missing from plugin.yml");
        }

        AgentExecCommand execCommand = new AgentExecCommand(this);
        var execCmd = getCommand("agentexec");
        if (execCmd != null) {
            execCmd.setExecutor(execCommand);
        } else {
            getLogger().severe("Command 'agentexec' missing from plugin.yml");
        }

        getLogger().info("NeighborhoodAgent enabled -> " + orchestrator.getBaseUrl());
    }

    @Override
    public void onDisable() {
        if (orchestrator != null) {
            orchestrator.close();
        }
    }

    public OrchestratorClient getOrchestrator() {
        return orchestrator;
    }
}
