package com.neighborhood.agent;

import org.bukkit.plugin.java.JavaPlugin;

public final class NeighborhoodAgentPlugin extends JavaPlugin {

    private CompanionGateway gateway;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        gateway = new CompanionGateway(this);
        AgentCommand agentCommand = new AgentCommand(this, gateway);
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

        gateway.start();
        getLogger().info("Neighborhood sidekick enabled -> " + gateway.getGatewayUrl());
    }

    @Override
    public void onDisable() {
        if (gateway != null) {
            gateway.close();
        }
    }

    public CompanionGateway getGateway() {
        return gateway;
    }
}
