"""Single execute path for companion tools."""

from agent.dispatch.execute import execute
from agent.dispatch.protocol import DispatchTransport, PluginNativeProtocol

__all__ = ["DispatchTransport", "PluginNativeProtocol", "execute"]
